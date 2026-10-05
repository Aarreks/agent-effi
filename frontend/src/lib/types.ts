export type CaseStatus = 'new'|'in_progress'|'resolved';
export type Note = {text:string;at:string;actor:string;call_id:string|null};
export type Audit = {at:string;actor:string;call_id:string|null;revision:number;fields:Record<string,{before:unknown;after:unknown}>};
export type CaseRecord = {id:string;name:string;phone:string;issue_type:string;description:string;location:string;status:CaseStatus;notes:Note[];revision:number;created_at:string;updated_at:string;audit?:Audit[]};
export type Analysis = {summary:string;caller_name:string|null;phone:string|null;issue_type:string|null;location:string|null;outcome:string;follow_up:string[]};
export type CallRecord = {id:string;status:string;mode:string;case_id:string|null;case_ids?:string[];started_at:string;ended_at:string|null;analysis_status:string;analysis:Analysis|null;analysis_error?:string;error?:string;live_caption?:{role:string;text:string}|null;intake?:Record<string,string>;intake_stage?:string;supervisor_status?:string;supervisor_reviews?:{event_id:string;at:string;status:string;utterance:string;reason:string;correction:string}[];transcript?:{id:string;role:string;text:string;at:string}[]};
