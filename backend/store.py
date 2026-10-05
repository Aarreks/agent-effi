"""One SQLite transaction per mutation; call IDs make voice creation retry-safe."""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def phone_key(value):
    return ''.join(c for c in value if c.isdigit())[-10:]


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
              PRAGMA journal_mode=WAL;
              CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS calls(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS turns(call_id TEXT, event_id TEXT, payload TEXT NOT NULL,
                PRIMARY KEY(call_id,event_id), FOREIGN KEY(call_id) REFERENCES calls(id));
              CREATE TABLE IF NOT EXISTS changes(id INTEGER PRIMARY KEY, case_id TEXT, payload TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS actions(call_id TEXT, action_id TEXT, request TEXT, result TEXT,
                PRIMARY KEY(call_id,action_id));
              CREATE TABLE IF NOT EXISTS creations(call_id TEXT, intake_id TEXT, request TEXT, result TEXT,
                PRIMARY KEY(call_id,intake_id));
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get(self, db, table, identity):
        row = db.execute(f'SELECT payload FROM {table} WHERE id=?', (identity,)).fetchone()
        if row is None:
            raise KeyError(identity)
        return json.loads(row['payload'])

    def save(self, db, table, value):
        db.execute(f'INSERT INTO {table}(id,payload) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                   (value['id'], json.dumps(value)))

    def listing(self, table):
        with self.db() as db:
            return [json.loads(r['payload']) for r in db.execute(f'SELECT payload FROM {table} ORDER BY rowid DESC')]

    def case(self, identity):
        with self.db() as db:
            case = self.get(db, 'cases', identity)
            case['audit'] = [json.loads(r['payload']) for r in db.execute('SELECT payload FROM changes WHERE case_id=? ORDER BY id', (identity,))]
            return case

    def call(self, identity):
        with self.db() as db:
            call = self.get(db, 'calls', identity)
            call['transcript'] = [json.loads(r['payload']) for r in db.execute('SELECT payload FROM turns WHERE call_id=? ORDER BY rowid', (identity,))]
            return call

    def start_call(self, mode='voice'):
        call = dict(id=str(uuid.uuid4()), status='connecting' if mode == 'voice' else 'active',
                    mode=mode, case_id=None, case_ids=[],intake_id=str(uuid.uuid4()),started_at=now(), ended_at=None,
                    analysis_status='pending', analysis=None,intake={},intake_stage='collecting',
                    intake_history=[],supervisor_status='pending',supervisor_reviews=[])
        with self.db() as db:
            self.save(db, 'calls', call)
        return call

    def update_call(self, identity, **fields):
        with self.db() as db:
            call = self.get(db, 'calls', identity)
            call.update(fields)
            self.save(db, 'calls', call)
        return call

    def turn(self, identity, event_id, role, text,action_ids=()):
        with self.db() as db:
            call=self.get(db, 'calls', identity)
            value = dict(id=event_id, role=role, text=text, at=now())
            if role=='assistant':
                value['case_snapshot']=self.get(db,'cases',call['case_id']) if call['case_id'] else None
                value['case_snapshots']=[self.get(db,'cases',case_id) for case_id in dict.fromkeys(call.get('case_ids',[])+([call['case_id']] if call['case_id'] else []))]
            if action_ids:
                if role!='assistant':raise ValueError('Only assistant replies may reference saved actions')
                receipts=[]
                for action_id in dict.fromkeys(action_ids):
                    action=db.execute('SELECT request,result FROM actions WHERE call_id=? AND action_id=?',(identity,action_id)).fetchone()
                    if not action:raise ValueError('Tool action is not confirmed for this call')
                    request=json.loads(action['request']);result=json.loads(action['result'])
                    note=request.get('fields',{}).get('note')
                    linked=set(call.get('case_ids',[])+([call['case_id']] if call['case_id'] else []))
                    if not note or request.get('case_id') not in linked or result.get('id')!=request.get('case_id'):
                        raise ValueError('Tool action does not confirm a note on the linked case')
                    receipts.append(dict(action_id=action_id,case_id=result['id'],kind='add_note',note=note,saved_at=result['updated_at']))
                value['confirmed_actions']=receipts
            existing = db.execute('SELECT payload FROM turns WHERE call_id=? AND event_id=?',(identity,event_id)).fetchone()
            if existing:
                old=json.loads(existing['payload'])
                if old['text'] != text or old['role'] != role or old.get('confirmed_actions',[])!=value.get('confirmed_actions',[]):
                    raise ValueError('Transcript event ID reused with different content')
                return old
            db.execute('INSERT INTO turns VALUES(?,?,?)',(identity,event_id,json.dumps(value)))
            return value

    def update_intake(self, identity, fields, stage='collecting',start_new=False,reset_id=None):
        with self.db() as db:
            call=self.get(db,'calls',identity)
            if call['status'] in {'ended','failed'}:raise ValueError('This call has ended')
            if start_new:
                if fields:raise ValueError('Starting a new report cannot also supply contact or issue fields. Collect them after the reset.')
                if reset_id:
                    existing=db.execute('SELECT request FROM actions WHERE call_id=? AND action_id=?',(identity,reset_id)).fetchone()
                    if existing:
                        if json.loads(existing['request'])!={'kind':'start_intake'}:raise ValueError('Action ID reused with different content')
                        return call  # A reset retry must not discard a later draft or saved case.
                if call['case_id'] or call.get('intake'):
                    call.setdefault('workflow_history',[]).append(dict(at=now(),previous_case_id=call['case_id'],previous_intake=call.get('intake',{}),event='new_intake'))
                if call['case_id']:
                    call['case_ids']=list(dict.fromkeys(call.get('case_ids',[])+[call['case_id']]))
                call.pop('created_request',None)
                call.update(case_id=None,intake={},intake_stage='collecting',intake_id=str(uuid.uuid4()))
                self.save(db,'calls',call)
                if reset_id:db.execute('INSERT INTO actions VALUES(?,?,?,?)',(identity,reset_id,json.dumps({'kind':'start_intake'}),json.dumps(call)))
            if call['case_id']:raise ValueError('The case is already linked. Start fresh intake explicitly for a separate request, or add a note to the existing case.')
            intake={**call.get('intake',{}),**fields}
            if intake != call.get('intake',{}) or stage != call.get('intake_stage','collecting'):
                call.update(intake=intake,intake_stage=stage)
                call.setdefault('intake_history',[]).append(dict(at=now(),fields=fields,stage=stage))
                self.save(db,'calls',call)
            return call

    def supervisor_review(self, identity, event_id, fields):
        with self.db() as db:
            call=self.get(db,'calls',identity)
            turn=db.execute('SELECT payload FROM turns WHERE call_id=? AND event_id=?',(identity,event_id)).fetchone()
            if not turn or json.loads(turn['payload'])['role']!='assistant' or json.loads(turn['payload'])['text']!=fields['utterance']:
                raise ValueError('Supervisor review must reference an actual assistant transcript event')
            reviews=call.setdefault('supervisor_reviews',[])
            existing=next((r for r in reviews if r['event_id']==event_id),None)
            if existing:
                if any(existing.get(k)!=v for k,v in fields.items()):raise ValueError('Review event ID reused with different content')
                return call
            reviews.append(dict(event_id=event_id,at=now(),**fields))
            call['supervisor_status']='needs_attention' if any(r['status'] in {'corrected','failed'} for r in reviews) else 'monitoring'
            self.save(db,'calls',call)
            return call

    def audit(self, db, case, before, actor, call_id):
        fields = {k:dict(before=before.get(k),after=case[k]) for k in case if k not in {'updated_at','revision','notes'} and before.get(k) != case[k]}
        if before.get('notes') != case['notes']:
            fields['notes'] = dict(before=before.get('notes',[]),after=case['notes'])
        db.execute('INSERT INTO changes(case_id,payload) VALUES(?,?)',
                   (case['id'],json.dumps(dict(at=now(), actor=actor, call_id=call_id, revision=case['revision'],fields=fields))))

    def create_case(self, call_id, fields,intake_id=None):
        with self.db() as db:
            call = self.get(db,'calls',call_id)
            scope=intake_id or call.get('intake_id',call_id)
            request=json.dumps(fields,sort_keys=True)
            previous=db.execute('SELECT request,result FROM creations WHERE call_id=? AND intake_id=?',(call_id,scope)).fetchone()
            if previous:
                if previous['request']!=request:raise ValueError('Creation retry changed the confirmed report')
                saved=json.loads(previous['result'])
                if intake_id is None and call['case_id'] and call['case_id']!=saved['id']:
                    raise ValueError('This intake is now linked to a different case')
                return saved
            if scope!=call.get('intake_id',call_id):raise ValueError('Intake changed. Read and confirm the current report before saving.')
            if call['status'] in {'ended','failed'}:raise ValueError('This call has ended')
            if call['case_id']:
                if call.get('created_request') == json.dumps(fields,sort_keys=True):
                    return self.get(db,'cases',call['case_id'])
                raise ValueError('This intake already has a linked case. Start fresh intake for a separate request, or add a note to it.')
            stamp=now()
            case=dict(id='EG-'+uuid.uuid4().hex[:6].upper(), **fields, status='new', notes=[], revision=1,
                      created_at=stamp,updated_at=stamp)
            self.save(db,'cases',case)
            call['case_id']=case['id']
            call['case_ids']=list(dict.fromkeys(call.get('case_ids',[])+[case['id']]))
            call.update(intake=fields,intake_stage='recorded')
            call['created_request']=json.dumps(fields,sort_keys=True)
            self.save(db,'calls',call)
            db.execute('INSERT INTO creations VALUES(?,?,?,?)',(call_id,scope,request,json.dumps(case)))
            self.audit(db,case,{},'voice' if call['mode']=='voice' else 'test',call_id)
            return case

    def attach(self, call_id, case_id):
        with self.db() as db:
            case=self.get(db,'cases',case_id)
            call=self.get(db,'calls',call_id)
            if call['case_id'] != case_id:
                call.pop('created_request',None)
            call['case_id']=case_id
            call['case_ids']=list(dict.fromkeys(call.get('case_ids',[])+[case_id]))
            call['intake_stage']='case_found'
            self.save(db,'calls',call)
            return case

    def patch_case(self, identity, fields, actor='staff', call_id=None, action_id=None, revision=None):
        request=json.dumps({'case_id':identity,'fields':fields},sort_keys=True)
        with self.db() as db:
            if call_id:
                call=self.get(db,'calls',call_id)
                if call['case_id'] != identity:
                    raise ValueError('Look up this case in the current call before updating it')
            if action_id:
                old=db.execute('SELECT request,result FROM actions WHERE call_id=? AND action_id=?',(call_id,action_id)).fetchone()
                if old:
                    if old['request'] != request:
                        raise ValueError('Action ID reused with different content')
                    return json.loads(old['result'])
            case=self.get(db,'cases',identity)
            if revision is not None and revision != case['revision']:
                raise ValueError('Case changed. Refresh and try again.')
            before=json.loads(json.dumps(case))
            note=fields.get('note')
            case.update({k:v for k,v in fields.items() if k != 'note'})
            if actor=='staff' and 'location' in fields:
                # A staff decision supersedes earlier resident address proposals,
                # including an explicit confirmation of the unchanged address.
                case['location_reviewed_at']=now()
            if note:
                case['notes'].append(dict(text=note, at=now(),actor=actor,call_id=call_id))
            if case == before:
                return case
            case.update(revision=case['revision']+1,updated_at=now())
            self.save(db,'cases',case)
            self.audit(db,case,before,actor,call_id)
            if action_id:
                db.execute('INSERT INTO actions VALUES(?,?,?,?)',(call_id,action_id,request,json.dumps(case)))
            return case
