export class ApiError extends Error {
  constructor(message:string,public status:number) {super(message);this.name="ApiError"}
}
export function createJsonClient(base="/api") {
  return async function request<T>(path:string,options:RequestInit={}):Promise<T> {
    const headers=new Headers(options.headers);
    if(options.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");
    const response=await fetch(`${base}${path}`,{...options,headers});
    if(!response.ok){
      const body=await response.json().catch(()=>null);
      const detail=body?.detail;
      const message=typeof detail==="string"?detail:Array.isArray(detail)?detail.map((item:{loc:string[];msg:string})=>`${item.loc.slice(1).join(".")}: ${item.msg}`).join("; "):`Request failed (${response.status})`;
      throw new ApiError(message,response.status);
    }
    if(response.status===204)return undefined as T;
    return response.json() as Promise<T>;
  };
}
export const api=createJsonClient();
export const errorMessage=(error:unknown)=>error instanceof Error?error.message:"Something went wrong. Please try again.";
