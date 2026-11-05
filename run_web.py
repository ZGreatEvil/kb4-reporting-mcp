import uvicorn
from config.settings import load_config
from web.main import app

if __name__ == "__main__":
    cfg=load_config()
    uvicorn.run(app,host=cfg.web_host,port=cfg.web_port)
