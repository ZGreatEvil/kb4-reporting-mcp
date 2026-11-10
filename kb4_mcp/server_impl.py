from typing import Optional

import httpx
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from config.settings import PRODUCTS, load_config
from kb4_mcp import outputs, products, summaries
from kb4_mcp.knowledge import NistSearch
from knowbe4.client import KnowBe4APIError, KnowBe4Client, readable_error

# kept under this name for mcp clients and tests
tool_message = readable_error


class ToolClient(KnowBe4Client):
    """turns KnowBe4 failures into ToolError, whose message the model can read; other exceptions are masked by the sdk"""

    async def get(self, console, path, params=None):
        try:
            return await super().get(console, path, params)
        except (KnowBe4APIError, httpx.HTTPError, ValueError) as exc:
            raise ToolError(readable_error(exc)) from exc

    async def graph(self, console, product, document, variables=None):
        try:
            return await super().graph(console, product, document, variables)
        except (KnowBe4APIError, httpx.HTTPError, ValueError) as exc:
            raise ToolError(readable_error(exc)) from exc

    def has_product(self, console, product):
        # an unknown console must read "Unknown console", not the sdk's masked error
        try:
            return super().has_product(console, product)
        except ValueError as exc:
            raise ToolError(readable_error(exc)) from exc

    async def list_user_events(self, console, params=None):
        try:
            return await super().list_user_events(console, params)
        except (KnowBe4APIError, httpx.HTTPError, ValueError) as exc:
            raise ToolError(readable_error(exc)) from exc


CONFIG=load_config()
KB4=ToolClient(CONFIG)
NIST=NistSearch()
mcp=MCPServer("KnowBe4 Multi-Console Reporting", instructions="Read-only KnowBe4 Reporting API server. Prefer the summary tools; never reveal API keys.", version="1.1.0")

@mcp.tool(description="Forget the cached KnowBe4 answers for one console so the next calls fetch fresh data (at most once a minute). Use only when the user explicitly asks for fresh data.")
def refresh_data(console:str)->dict:
    if console.lower().strip() not in CONFIG.consoles:
        raise ToolError(f"Unknown console '{console}'.")
    return KB4.clear_cache(console)
@mcp.tool(description="List configured consoles, whether each has an API key, and KnowBe4 requests used in the last 24 hours.")
def list_consoles()->dict:
    return {"consoles":[{"id":k,"display_name":c.display_name,"region":c.region,"base_url":c.base_url,"available":c.has_api_key,"api_usage":KB4.usage_summary(k),
                         # product apis: which keys are set, and their requests in the last 24 h (counted apart from the reporting limit)
                         "product_apis":{p:{"key":True,"requests_last_24h":KB4.usage.used(f"{k}:{p}")} for p in PRODUCTS if c.product_key(p)}} for k,c in CONFIG.consoles.items()]}

# summary tools: computed in python, small results; the chat model should prefer these
@mcp.tool(description="PREFER for comparisons: current risk score of every console, ranked, plus consoles without a key.")
async def compare_consoles_risk()->dict: return await summaries.compare_consoles_risk(KB4,CONFIG)
@mcp.tool(description="PREFER for riskiest users: top users by current_risk_score (status: active, archived or empty for all).")
async def top_users_by_risk(console:str,limit:int=10,status:str="active")->dict: return await summaries.top_users_by_risk(KB4,console,limit,status)
@mcp.tool(description="PREFER for finding a person: search users by name, email, job title or department; returns ids.")
async def find_user(console:str,query:str,limit:int=10)->dict: return await summaries.find_user(KB4,console,query,limit)
@mcp.tool(description="PREFER for phishing tests: latest (sort=latest) or worst (sort=highest_ppp) tests with phish-prone %. Optional period: start_date / end_date (YYYY-MM-DD).")
async def phishing_campaign_summary(console:str,limit:int=10,sort:str="latest",start_date:Optional[str]=None,end_date:Optional[str]=None)->dict: return await summaries.phishing_campaign_summary(KB4,console,limit,sort,start_date,end_date)
@mcp.tool(description="PREFER for training: campaigns newest first with completion %, optional campaign_id or start-date range (YYYY-MM-DD).")
async def training_completion_summary(console:str,campaign_id:Optional[int]=None,start_date:Optional[str]=None,end_date:Optional[str]=None,limit:int=10)->dict: return await summaries.training_completion_summary(KB4,console,campaign_id,start_date,end_date,limit)
@mcp.tool(description="PREFER for the organisation's risk: current score and level, 30/90-day change, 3-month average, and why (phishing failures, users per level). Optional period: start_date / end_date (YYYY-MM-DD).")
async def account_risk_overview(console:str,start_date:Optional[str]=None,end_date:Optional[str]=None)->dict: return await summaries.account_risk_overview(KB4,console,start_date,end_date)
@mcp.tool(description="PREFER for one person's risk or risk history (needs the id from find_user): score, level, trend, 3-month average, and why (phishing, training status). Optional period: start_date / end_date (YYYY-MM-DD).")
async def user_risk_summary(console:str,user_id:int,start_date:Optional[str]=None,end_date:Optional[str]=None)->dict: return await summaries.user_risk_summary(KB4,console,user_id,start_date,end_date)
@mcp.tool(description="PREFER for charts/graphs: draws one and attaches it. chart = risk_trend (line; user_id for one person), users_by_level (pie), top_users (bar), phishing_tests (bar), training_completion (bar), groups (bar, riskiest groups), modules (bar, completion per training module), group_trend (line; group_id from group_risk_trend), reported_emails (bar, emails reported to PhishER per month). Optional period: start_date / end_date (YYYY-MM-DD).")
async def make_chart(console:str,chart:str,user_id:Optional[int]=None,limit:int=10,language:str="id",start_date:Optional[str]=None,end_date:Optional[str]=None,group_id:Optional[int]=None)->dict: return await outputs.make_chart(KB4,console,chart,language,user_id,limit,start_date,end_date,group_id)
@mcp.tool(description="Export data as a CSV file download (export, CSV, Excel, unduh). dataset = users (status: active by default, archived, or all), phishing_tests, training_campaigns, risk_history (the organisation's history: leave user_id out; one person: their numeric user_id), modules (training progress per module), reported_emails (emails reported to PhishER; needs the PhishER key). Optional period: start_date / end_date (YYYY-MM-DD).")
async def export_csv(console:str,dataset:str,user_id:Optional[int]=None,status:str="active",start_date:Optional[str]=None,end_date:Optional[str]=None)->dict: return await outputs.export_csv(KB4,console,dataset,user_id,status,start_date,end_date)
@mcp.tool(description="Search official NIST guidance (SP 800-50r1 awareness and training programmes, CSF 2.0, NIST Phish Scale). query in ENGLISH keywords. For best practice, framework or 'what does NIST say' questions.")
def search_nist(query:str,limit:int=4)->dict: return NIST.search(query,limit)
@mcp.tool(description="PREFER for listing users: one page (default 20) sorted by risk or name, with the total and next_offset for 'show more'.")
async def list_users_page(console:str,status:str="active",sort:str="risk",offset:int=0,limit:int=20)->dict: return await summaries.list_users_page(KB4,console,status,sort,offset,limit)
@mcp.tool(description="PREFER for groups, teams or departments: which groups are riskiest (KnowBe4 group risk score, members, phish-prone %). by=group (default) or department/location/division.")
async def risk_by_group(console:str,by:str="group",limit:int=10)->dict: return await summaries.risk_by_group(KB4,console,by,limit)
@mcp.tool(description="PREFER for repeat clickers: people who failed two or more of the latest phishing tests (tests = how many recent tests to check, max 12). Optional period: start_date / end_date (YYYY-MM-DD).")
async def repeat_phishing_failures(console:str,tests:int=6,limit:int=10,start_date:Optional[str]=None,end_date:Optional[str]=None)->dict: return await summaries.repeat_phishing_failures(KB4,console,tests,limit,start_date,end_date)
@mcp.tool(description="PREFER for one phishing test in detail: who clicked or failed, who reported it, report rate, how fast people failed, who opened but did nothing. Latest test (in the period, if given) unless pst_id is given. Optional period: start_date / end_date (YYYY-MM-DD).")
async def phishing_test_detail(console:str,pst_id:Optional[int]=None,limit:int=20,start_date:Optional[str]=None,end_date:Optional[str]=None)->dict: return await summaries.phishing_test_detail(KB4,console,pst_id,limit,start_date,end_date)
@mcp.tool(description="PREFER for overdue, past-due or unfinished training: how many enrolments are Past Due, who has the most, which modules. Optional period: start_date / end_date (YYYY-MM-DD).")
async def overdue_training(console:str,limit:int=10,start_date:Optional[str]=None,end_date:Optional[str]=None)->dict: return await summaries.overdue_training(KB4,console,limit,start_date,end_date)
@mcp.tool(description="PREFER for training MODULES (modul, course, video, materi) and their progress (watched, passed, finished, not started, overdue, time spent): per module enrolled, passed, Past Due, not started, completion %, typical minutes, and facts that explain each result. Episodes of one series are one row. module = words from one module's name to focus on it (each episode then shown). sort = least_completed (default), most_overdue, most_enrolled, most_completed (best) or longest.")
async def training_by_module(console:str,module:Optional[str]=None,sort:str="least_completed",limit:int=10,start_date:Optional[str]=None,end_date:Optional[str]=None)->dict: return await summaries.training_by_module(KB4,console,module,sort,limit,start_date,end_date)
@mcp.tool(description="Only for which training content the company HAS (library, purchased items): types, length, publish and purchase dates, retired, never assigned. sort = most_used (default), newest (by KnowBe4 publish date) or recently_purchased. For newest / terbaru / recommend questions. Not for progress (watched, passed, not started): use training_by_module. content_type filters, e.g. Video Module. Optional period: start_date / end_date (YYYY-MM-DD), published or added in it.")
async def training_library(console:str,content_type:Optional[str]=None,limit:int=20,sort:str="most_used",start_date:Optional[str]=None,end_date:Optional[str]=None)->dict: return await summaries.training_library(KB4,console,content_type,limit,sort,start_date,end_date)
@mcp.tool(description="PREFER for a group's risk over time (is a group getting better or worse): group = words from the group name; without group, the 90-day change of the riskiest groups. Optional period: start_date / end_date (YYYY-MM-DD).")
async def group_risk_trend(console:str,group:Optional[str]=None,limit:int=5,start_date:Optional[str]=None,end_date:Optional[str]=None)->dict: return await summaries.group_risk_trend(KB4,console,group,limit,start_date,end_date)
@mcp.tool(description="PREFER for sign-ins: who never signed in to KnowBe4 and who has not signed in for a long time (active users).")
async def sign_in_activity(console:str,limit:int=20)->dict: return await summaries.sign_in_activity(KB4,console,limit)
@mcp.tool(description="PREFER for new employees / new joiners / karyawan baru: people who joined in the period and how their risk, phishing and training compare with everyone else. Optional period: start_date / end_date (YYYY-MM-DD).")
async def new_joiners(console:str,limit:int=10,start_date:Optional[str]=None,end_date:Optional[str]=None)->dict: return await summaries.new_joiners(KB4,console,limit,start_date,end_date)
@mcp.tool(description="PREFER for callback / phone / voice phishing (vishing): who called the number in the email and who gave data on the call. Optional period: start_date / end_date (YYYY-MM-DD).")
async def callback_phishing_summary(console:str,limit:int=10,start_date:Optional[str]=None,end_date:Optional[str]=None)->dict: return await summaries.callback_phishing_summary(KB4,console,limit,start_date,end_date)

# product apis (KSAT, PhishER, PasswordIQ, Real-Time Coaching graph apis; User Event api): read-only, need their own keys
@mcp.tool(description="PREFER for benchmarks / industry comparison: our phish-prone % against KnowBe4's official industry benchmark (before training, 90 days, 1-3 years) for our company size. industry = another industry to compare with, e.g. banking.")
async def industry_benchmark(console:str,industry:Optional[str]=None)->dict: return await products.industry_benchmark(KB4,console,industry)
@mcp.tool(description="PREFER for emails employees REPORTED as suspicious (PhishER, Phish Alert Button): how many, threat / spam / clean, still open, top reporters, latest. category = threat, spam, clean or unknown; status = received, in_review or resolved. Optional period: start_date / end_date (YYYY-MM-DD).")
async def reported_emails(console:str,category:Optional[str]=None,status:Optional[str]=None,limit:int=10,start_date:Optional[str]=None,end_date:Optional[str]=None)->dict: return await products.reported_emails(KB4,console,category,status,limit,start_date,end_date)
@mcp.tool(description="PREFER for PhishER rules: which rules exist, active or not, and how many reported emails each matched.")
async def phisher_rules(console:str,limit:int=20)->dict: return await products.phisher_rules(KB4,console,limit)
@mcp.tool(description="PREFER for USB drive tests (flash drives left out): who opened files or enabled macros.")
async def usb_test_results(console:str,limit:int=10)->dict: return await products.usb_test_results(KB4,console,limit)
@mcp.tool(description="PREFER for physical QR code tests (posters, flyers): scans and data entered per location.")
async def physical_qr_results(console:str)->dict: return await products.physical_qr_results(KB4,console)
@mcp.tool(description="PREFER for which simulations / campaign types the account runs: email phishing (standard, callback, vishing), USB, physical QR, AIDA, Second Chance.")
async def simulation_overview(console:str)->dict: return await products.simulation_overview(KB4,console)
@mcp.tool(description="PREFER for admin changes / audit log: what admins changed in KnowBe4, who and when. category = phishing, training, users, account, etc. Optional period: start_date / end_date (YYYY-MM-DD); default the last 90 days.")
async def admin_audit_log(console:str,category:Optional[str]=None,limit:int=15,start_date:Optional[str]=None,end_date:Optional[str]=None)->dict: return await products.admin_audit_log(KB4,console,category,limit,start_date,end_date)
@mcp.tool(description="PREFER for Real-Time Coaching / SecurityCoach: setup, coaching sent, people coached, repeat offenders. Optional period: start_date / end_date (YYYY-MM-DD).")
async def security_coaching(console:str,start_date:Optional[str]=None,end_date:Optional[str]=None)->dict: return await products.security_coaching(KB4,console,start_date,end_date)
@mcp.tool(description="PREFER for password risks (PasswordIQ): weak, shared, breached or never-expiring Active Directory passwords from the last scan.")
async def password_risks(console:str)->dict: return await products.password_risks(KB4,console)
@mcp.tool(description="PREFER for events from other security tools (User Event API): event types, sources, users. user_email filters one person. Optional period: start_date / end_date (YYYY-MM-DD).")
async def user_events(console:str,user_email:Optional[str]=None,limit:int=10,start_date:Optional[str]=None,end_date:Optional[str]=None)->dict: return await products.user_events(KB4,console,user_email,limit,start_date,end_date)
@mcp.tool(description="PREFER for which KnowBe4 products are set up / in use (PhishER, PasswordIQ, Real-Time Coaching, KSAT, User Events).")
async def product_status(console:str)->dict: return await products.product_status(KB4,console)
@mcp.tool(description="Account name, subscription and current risk score for one console.")
async def knowbe4_health_check(console:str)->dict: return await KB4.health_check(console)
def _with_level(record):
    # the model gave 38.01 the level "Medium" from the bare score; the KnowBe4 level is added here
    if isinstance(record,dict) and isinstance(record.get("current_risk_score"),(int,float)):
        return {**record,"current_risk_level":summaries.risk_level(record["current_risk_score"]),"risk_scale":summaries.RISK_SCALE_NOTE}
    return record
@mcp.tool(description="Full account details for one console, including current_risk_score and its KnowBe4 level.")
async def get_account(console:str)->dict: return _with_level(await KB4.get_account(console))
@mcp.tool(description="Account risk score over time (full=true for the complete history).")
async def get_account_risk_score_history(console:str, full:bool=False)->list: return await KB4.get_account_risk_history(console,full)
@mcp.tool(description="Raw user records; large. Use find_user or top_users_by_risk instead where possible.")
async def list_users(console:str,status:Optional[str]=None,group_id:Optional[int]=None,max_records:Optional[int]=None)->list: return await KB4.list_users(console,status,group_id,max_records)
@mcp.tool(description="One user by id, including current_risk_score and its KnowBe4 level.")
async def get_user(console:str,user_id:int)->dict: return _with_level(await KB4.get_user(console,user_id))
@mcp.tool(description="One user's risk score over time (full=true for the complete history).")
async def get_user_risk_score_history(console:str,user_id:int,full:bool=False)->list: return await KB4.get_user_risk_history(console,user_id,full)
@mcp.tool(description="Groups in a console.")
async def list_groups(console:str,status:Optional[str]=None,max_records:Optional[int]=None)->list: return await KB4.list_groups(console,status,max_records)
@mcp.tool(description="One group's risk score over time (full=true for the complete history).")
async def get_group_risk_score_history(console:str,group_id:int,full:bool=False)->list: return await KB4.get_group_risk_history(console,group_id,full)
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
    if not CONFIG.enable_raw_get:
        raise RuntimeError("knowbe4_raw_get is disabled")
    return await KB4.get(console,path,params)

def run_mcp()->None:
    mcp.run(transport="streamable-http",host=CONFIG.mcp_host,port=CONFIG.mcp_port,streamable_http_path=CONFIG.mcp_path,json_response=True,stateless_http=True,max_request_body_size=8*1024*1024)

if __name__=="__main__":
    run_mcp()
