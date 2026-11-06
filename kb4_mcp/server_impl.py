import httpx
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from config.settings import load_config
from knowbe4.client import KnowBe4APIError, KnowBe4Client, KnowBe4DailyLimitError
from kb4_mcp import summaries

from typing import Optional

STATUS_HINTS = {
    401: "the API key was rejected (wrong, expired, or not a Reporting API key)",
    403: "the API key is not allowed to read this data",
    404: "not found; check the id",
    429: "KnowBe4 rate limit hit; try again in a few minutes",
}


def tool_message(exc: Exception) -> str:
    if isinstance(exc, KnowBe4DailyLimitError):
        return (f"KnowBe4 daily API limit reached for this console ({exc.used} of {exc.limit} requests "
                "in the last 24 hours). Tell the user to try again later.")
    if isinstance(exc, KnowBe4APIError):
        return f"KnowBe4 API error {exc.status_code}: {STATUS_HINTS.get(exc.status_code, 'the request failed')}."
    if isinstance(exc, httpx.HTTPError):
        return "KnowBe4 could not be reached (network error or timeout). Try again later."
    return str(exc)


class ToolClient(KnowBe4Client):
    """turns KnowBe4 failures into ToolError, whose message the model can read; other exceptions are masked by the sdk"""

    async def get(self, console, path, params=None):
        try:
            return await super().get(console, path, params)
        except (KnowBe4APIError, httpx.HTTPError, ValueError) as exc:
            raise ToolError(tool_message(exc)) from exc


CONFIG=load_config()
KB4=ToolClient(CONFIG)
mcp=MCPServer("KnowBe4 Multi-Console Reporting", instructions="Read-only KnowBe4 Reporting API server. Prefer the summary tools; never reveal API keys.", version="1.1.0")

@mcp.tool(description="List configured consoles, whether each has an API key, and KnowBe4 requests used in the last 24 hours.")
def list_consoles()->dict:
    return {"consoles":[{"id":k,"display_name":c.display_name,"region":c.region,"base_url":c.base_url,"available":c.has_api_key,"api_usage":KB4.usage_summary(k)} for k,c in CONFIG.consoles.items()]}

# summary tools: computed in python, small results; the chat model should prefer these
@mcp.tool(description="PREFER for comparisons: current risk score of every console, ranked, plus consoles without a key.")
async def compare_consoles_risk()->dict: return await summaries.compare_consoles_risk(KB4,CONFIG)
@mcp.tool(description="PREFER for riskiest users: top users by current_risk_score (status: active, archived or empty for all).")
async def top_users_by_risk(console:str,limit:int=10,status:str="active")->dict: return await summaries.top_users_by_risk(KB4,console,limit,status)
@mcp.tool(description="PREFER for finding a person: search users by name, email, job title or department; returns ids.")
async def find_user(console:str,query:str,limit:int=10)->dict: return await summaries.find_user(KB4,console,query,limit)
@mcp.tool(description="PREFER for phishing tests: latest (sort=latest) or worst (sort=highest_ppp) tests with phish-prone %.")
async def phishing_campaign_summary(console:str,limit:int=10,sort:str="latest")->dict: return await summaries.phishing_campaign_summary(KB4,console,limit,sort)
@mcp.tool(description="PREFER for training: campaigns newest first with completion %, optional campaign_id or start-date range (YYYY-MM-DD).")
async def training_completion_summary(console:str,campaign_id:Optional[int]=None,start_date:Optional[str]=None,end_date:Optional[str]=None,limit:int=10)->dict: return await summaries.training_completion_summary(KB4,console,campaign_id,start_date,end_date,limit)

@mcp.tool(description="Account name, subscription and current risk score for one console.")
async def knowbe4_health_check(console:str)->dict: return await KB4.health_check(console)
@mcp.tool(description="Full account details for one console, including current_risk_score.")
async def get_account(console:str)->dict: return await KB4.get_account(console)
@mcp.tool(description="Account risk score over time (full=true for the complete history).")
async def get_account_risk_score_history(console:str, full:bool=False)->list: return await KB4.get_account_risk_history(console,full)
@mcp.tool(description="Raw user records; large. Use find_user or top_users_by_risk instead where possible.")
async def list_users(console:str,status:Optional[str]=None,group_id:Optional[int]=None,max_records:Optional[int]=None)->list: return await KB4.list_users(console,status,group_id,max_records)
@mcp.tool(description="One user by id.")
async def get_user(console:str,user_id:int)->dict: return await KB4.get_user(console,user_id)
@mcp.tool(description="One user's risk score over time (full=true for the complete history).")
async def get_user_risk_score_history(console:str,user_id:int,full:bool=False)->list: return await KB4.get_user_risk_history(console,user_id,full)
@mcp.tool(description="Groups in a console.")
async def list_groups(console:str,status:Optional[str]=None,max_records:Optional[int]=None)->list: return await KB4.list_groups(console,status,max_records)
@mcp.tool(description="One group by id.")
async def get_group(console:str,group_id:int)->dict: return await KB4.get_group(console,group_id)
@mcp.tool(description="Members of one group.")
async def list_group_members(console:str,group_id:int,max_records:Optional[int]=None)->list: return await KB4.list_group_members(console,group_id,max_records)
@mcp.tool(description="Raw phishing campaigns (containers of security tests).")
async def list_phishing_campaigns(console:str,campaign_type:Optional[str]=None,max_records:Optional[int]=None)->list: return await KB4.list_phishing_campaigns(console,campaign_type,max_records)
@mcp.tool(description="One phishing campaign by id.")
async def get_phishing_campaign(console:str,campaign_id:int,campaign_type:Optional[str]=None): return await KB4.get_phishing_campaign(console,campaign_id,campaign_type)
@mcp.tool(description="Raw phishing security tests; use phishing_campaign_summary instead where possible.")
async def list_phishing_security_tests(console:str,campaign_type:Optional[str]=None,max_records:Optional[int]=None)->list: return await KB4.list_phishing_security_tests(console,campaign_type,max_records)
@mcp.tool(description="One phishing security test by pst_id.")
async def get_phishing_security_test(console:str,pst_id:int,campaign_type:Optional[str]=None): return await KB4.get_phishing_security_test(console,pst_id,campaign_type)
@mcp.tool(description="Recipients of one phishing security test; large.")
async def list_phishing_recipients(console:str,pst_id:int,campaign_type:Optional[str]=None,max_records:Optional[int]=None)->list: return await KB4.list_pst_recipients(console,pst_id,campaign_type,max_records)
@mcp.tool(description="One recipient of a phishing security test.")
async def get_phishing_recipient(console:str,pst_id:int,recipient_id:int,campaign_type:Optional[str]=None): return await KB4.get_pst_recipient(console,pst_id,recipient_id,campaign_type)
@mcp.tool(description="Raw training campaigns; use training_completion_summary instead where possible.")
async def list_training_campaigns(console:str,exclude_percentages:bool=False,max_records:Optional[int]=None)->list: return await KB4.list_training_campaigns(console,exclude_percentages,max_records)
@mcp.tool(description="One training campaign by id.")
async def get_training_campaign(console:str,campaign_id:int): return await KB4.get_training_campaign(console,campaign_id)
@mcp.tool(description="Training enrollments, filterable by campaign_id or user_id; large.")
async def list_training_enrollments(console:str,store_purchase_id:Optional[int]=None,campaign_id:Optional[int]=None,user_id:Optional[int]=None,exclude_archived_users:bool=False,include_campaign_id:bool=False,include_store_purchase_id:bool=False,include_employee_number:bool=False,max_records:Optional[int]=None)->list: return await KB4.list_training_enrollments(console,store_purchase_id,campaign_id,user_id,exclude_archived_users,include_campaign_id,include_store_purchase_id,include_employee_number,max_records)
@mcp.tool(description="One training enrollment by id.")
async def get_training_enrollment(console:str,enrollment_id:int): return await KB4.get_training_enrollment(console,enrollment_id)
@mcp.tool(description="Training content bought from the KnowBe4 store.")
async def list_training_store_purchases(console:str,max_records:Optional[int]=None)->list: return await KB4.list_store_purchases(console,max_records)
@mcp.tool(description="One store purchase by id.")
async def get_training_store_purchase(console:str,store_purchase_id:int): return await KB4.get_store_purchase(console,store_purchase_id)
@mcp.tool(description="Uploaded training policies.")
async def list_training_policies(console:str,max_records:Optional[int]=None)->list: return await KB4.list_policies(console,max_records)
@mcp.tool(description="One training policy by id.")
async def get_training_policy(console:str,policy_id:int): return await KB4.get_policy(console,policy_id)

@mcp.tool(description="Read-only GET against an allowed /v1/* Reporting API path.")
async def knowbe4_raw_get(console:str,path:str,params:Optional[dict]=None):
    if not CONFIG.enable_raw_get: raise RuntimeError("knowbe4_raw_get is disabled")
    return await KB4.get(console,path,params)

def run_mcp()->None:
    mcp.run(transport="streamable-http",host=CONFIG.mcp_host,port=CONFIG.mcp_port,streamable_http_path=CONFIG.mcp_path,json_response=True,stateless_http=True,max_request_body_size=8*1024*1024)

if __name__=="__main__": run_mcp()
