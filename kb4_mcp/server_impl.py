from mcp.server import MCPServer
from config.settings import load_config
from knowbe4.client import KnowBe4Client

from typing import Optional

CONFIG=load_config()
KB4=KnowBe4Client(CONFIG)
mcp=MCPServer("KnowBe4 Multi-Console Reporting", instructions="Read-only KnowBe4 Reporting API server. Use the semantic tools; never reveal API keys.", version="1.0.0")

@mcp.tool()
def list_consoles()->dict:
    """List configured consoles without secrets."""
    return {"consoles":[{"id":k,"display_name":c.display_name,"region":c.region,"base_url":c.base_url,"available":c.has_api_key} for k,c in CONFIG.consoles.items()]}

@mcp.tool()
async def knowbe4_health_check(console:str)->dict: return await KB4.health_check(console)
@mcp.tool()
async def get_account(console:str)->dict: return await KB4.get_account(console)
@mcp.tool()
async def get_account_risk_score_history(console:str, full:bool=False)->list: return await KB4.get_account_risk_history(console,full)
@mcp.tool()
async def list_users(console:str,status:Optional[str]=None,group_id:Optional[int]=None,max_records:Optional[int]=None)->list: return await KB4.list_users(console,status,group_id,max_records)
@mcp.tool()
async def get_user(console:str,user_id:int)->dict: return await KB4.get_user(console,user_id)
@mcp.tool()
async def get_user_risk_score_history(console:str,user_id:int,full:bool=False)->list: return await KB4.get_user_risk_history(console,user_id,full)
@mcp.tool()
async def list_groups(console:str,status:Optional[str]=None,max_records:Optional[int]=None)->list: return await KB4.list_groups(console,status,max_records)
@mcp.tool()
async def get_group(console:str,group_id:int)->dict: return await KB4.get_group(console,group_id)
@mcp.tool()
async def list_group_members(console:str,group_id:int,max_records:Optional[int]=None)->list: return await KB4.list_group_members(console,group_id,max_records)
@mcp.tool()
async def list_phishing_campaigns(console:str,campaign_type:Optional[str]=None,max_records:Optional[int]=None)->list: return await KB4.list_phishing_campaigns(console,campaign_type,max_records)
@mcp.tool()
async def get_phishing_campaign(console:str,campaign_id:int,campaign_type:Optional[str]=None): return await KB4.get_phishing_campaign(console,campaign_id,campaign_type)
@mcp.tool()
async def list_phishing_security_tests(console:str,campaign_type:Optional[str]=None,max_records:Optional[int]=None)->list: return await KB4.list_phishing_security_tests(console,campaign_type,max_records)
@mcp.tool()
async def get_phishing_security_test(console:str,pst_id:int,campaign_type:Optional[str]=None): return await KB4.get_phishing_security_test(console,pst_id,campaign_type)
@mcp.tool()
async def list_phishing_recipients(console:str,pst_id:int,campaign_type:Optional[str]=None,max_records:Optional[int]=None)->list: return await KB4.list_pst_recipients(console,pst_id,campaign_type,max_records)
@mcp.tool()
async def get_phishing_recipient(console:str,pst_id:int,recipient_id:int,campaign_type:Optional[str]=None): return await KB4.get_pst_recipient(console,pst_id,recipient_id,campaign_type)
@mcp.tool()
async def list_training_campaigns(console:str,exclude_percentages:bool=False,max_records:Optional[int]=None)->list: return await KB4.list_training_campaigns(console,exclude_percentages,max_records)
@mcp.tool()
async def get_training_campaign(console:str,campaign_id:int): return await KB4.get_training_campaign(console,campaign_id)
@mcp.tool()
async def list_training_enrollments(console:str,store_purchase_id:Optional[int]=None,campaign_id:Optional[int]=None,user_id:Optional[int]=None,exclude_archived_users:bool=False,include_campaign_id:bool=False,include_store_purchase_id:bool=False,include_employee_number:bool=False,max_records:Optional[int]=None)->list: return await KB4.list_training_enrollments(console,store_purchase_id,campaign_id,user_id,exclude_archived_users,include_campaign_id,include_store_purchase_id,include_employee_number,max_records)
@mcp.tool()
async def get_training_enrollment(console:str,enrollment_id:int): return await KB4.get_training_enrollment(console,enrollment_id)
@mcp.tool()
async def list_training_store_purchases(console:str,max_records:Optional[int]=None)->list: return await KB4.list_store_purchases(console,max_records)
@mcp.tool()
async def get_training_store_purchase(console:str,store_purchase_id:int): return await KB4.get_store_purchase(console,store_purchase_id)
@mcp.tool()
async def list_training_policies(console:str,max_records:Optional[int]=None)->list: return await KB4.list_policies(console,max_records)
@mcp.tool()
async def get_training_policy(console:str,policy_id:int): return await KB4.get_policy(console,policy_id)

@mcp.tool()
async def knowbe4_raw_get(console:str,path:str,params:Optional[dict]=None):
    """Read-only GET against an allowed /v1/* Reporting API path."""
    if not CONFIG.enable_raw_get: raise RuntimeError("knowbe4_raw_get is disabled")
    return await KB4.get(console,path,params)

def run_mcp()->None:
    mcp.run(transport="streamable-http",host=CONFIG.mcp_host,port=CONFIG.mcp_port,streamable_http_path=CONFIG.mcp_path,json_response=True,stateless_http=True,max_request_body_size=8*1024*1024)

if __name__=="__main__": run_mcp()
