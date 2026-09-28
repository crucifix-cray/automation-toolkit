import json, subprocess, os, sys

R = "/home/alan/.railway/bin/railway"


def env(n):
    e = {k: v for k, v in os.environ.items()
         if k not in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")}
    e["HOME"] = f"/home/alan/Documents/railways/sessions/session-{n}"
    e["LD_PRELOAD"] = ""
    return e


def api(n, q):
    r = subprocess.run([R, "api", q], capture_output=True, text=True,
                       timeout=120, env=env(n))
    try:
        return json.loads(r.stdout)
    except Exception:
        return {"raw": (r.stdout or "")[-300:] + (r.stderr or "")[-300:]}


def find_project(n, proj):
    r = subprocess.run([R, "list", "--json"], capture_output=True, text=True,
                       timeout=90, env=env(n))
    for x in json.loads(r.stdout):
        if x["name"] == proj and not x.get("deletedAt"):
            return x
    return None


def env_id(p):
    return p["environments"]["edges"][0]["node"]["id"]


def existing_service(n, p, name):
    for e in (p.get("services") or {}).get("edges", []):
        if e["node"]["name"] == name:
            return e["node"]["id"]
    return None


def create(n, proj, svc):
    p = find_project(n, proj)
    if not p:
        return {"err": f"project {proj} not found/not live"}
    sid = existing_service(n, p, svc)
    if sid:
        return {"project": p["id"], "env": env_id(p), "service": sid, "created": False}
    q = ('mutation { serviceCreate(input: { projectId: "%s", environmentId: "%s", '
         'name: "%s", source: { image: "ubuntu:24.04" } }) { id name } }'
         % (p["id"], env_id(p), svc))
    res = api(n, q)
    d = (res.get("data") or {}).get("serviceCreate")
    if not d:
        return {"err": json.dumps(res)[:300]}
    return {"project": p["id"], "env": env_id(p), "service": d["id"], "created": True}


def configure_and_deploy(n, service_id, env, start="sleep infinity"):
    q = ('mutation { serviceInstanceUpdate(serviceId: "%s", input: { '
         'startCommand: "%s", restartPolicyType: ALWAYS, restartPolicyMaxRetries: 5 }) }'
         % (service_id, start))
    r1 = api(n, q)
    q2 = ('mutation { serviceInstanceDeploy(serviceId: "%s", environmentId: "%s") }'
          % (service_id, env))
    r2 = api(n, q2)
    return {"update": json.dumps(r1)[:200], "deploy": json.dumps(r2)[:250]}


def instance_id(n, service_id, env):
    q = ('query { serviceInstance(environmentId: "%s", serviceId: "%s") { id } }'
         % (env, service_id))
    d = (api(n, q).get("data") or {}).get("serviceInstance") or {}
    return d.get("id")


def status(n, service_id, env):
    q = ('query { serviceInstance(environmentId: "%s", serviceId: "%s") { id '
         'latestDeployment { id status } } }' % (env, service_id))
    d = (api(n, q).get("data") or {}).get("serviceInstance") or {}
    dep = d.get("latestDeployment") or {}
    return d.get("id"), dep.get("status")


if __name__ == "__main__":
    sn, proj, svc = int(sys.argv[1]), sys.argv[2], sys.argv[3]
    info = create(sn, proj, svc)
    print(json.dumps(info))
    if "service" in info:
        print(json.dumps(configure_and_deploy(sn, info["service"], info["env"])))
        print("instance:", instance_id(sn, info["service"], info["env"]))
