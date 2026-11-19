"""Enable index-scoped internal HEC on the isolated local demo."""
import configparser
import json
from admin import Client, AdminError

c = Client()
p = configparser.ConfigParser()
p.read("/tmp/mtn-hec-inputs.conf")
token = p["http://mtn-demo"]["token"]
try:
    c.request("/servicesNS/nobody/system/configs/conf-inputs/http", "POST", form={"serverCert": "/run/splunk-tls/server.pem", "enableSSL": "1", "disabled": "0"})
    base = "/servicesNS/nobody/splunk_httpinput/data/inputs/http"
    try:
        c.request(base + "/mtn-demo")
    except AdminError as e:
        if e.status != 404:
            raise
        c.request(base, "POST", form={"name": "mtn-demo", "token": token, "index": "phoenix_app", "indexes": "phoenix_app,phoenix_net,phoenix_auth", "sourcetype": "phoenix:json", "disabled": "0"})
    c.request("/services/data/inputs/http/http/enable", "POST", form={})
    print(json.dumps({"internal_hec_configured": True, "tls": True, "indexes": ["phoenix_app", "phoenix_net", "phoenix_auth"]}))
except AdminError as e:
    print(json.dumps({"failed_endpoint": e.path, "status": e.status}))
    raise SystemExit(1)
