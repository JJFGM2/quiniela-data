#!/usr/bin/env python3
"""Runs INSIDE the GitHub Action (free, server-side). Fetches ESPN, maps by team
name, computes standings/groups/concentrado with the PROVEN scoring, and writes
data.json — the small "live table" the website reads from raw.githubusercontent.com.

No HTML, no template. Just the computed data the page renders.
"""
import json, os, urllib.request, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)  # repo root (script lives in scripts/)
B = json.load(open(os.path.join(ROOT, "quiniela_data.json"), encoding="utf-8"))
participants, fixtures = B["participants"], B["fixtures"]
teams, gpred, kpred = B["teams"], B["gpred"], B["kpred"]

ESPN_TO_ES = {
    "Mexico":"México","South Africa":"Sudáfrica","South Korea":"Corea Sur","Czechia":"Chequia",
    "Canada":"Canadá","Bosnia-Herzegovina":"Bosnia y H.","Bosnia and Herzegovina":"Bosnia y H.",
    "United States":"EE. UU.","USA":"EE. UU.","Paraguay":"Paraguay","Qatar":"Katar","Switzerland":"Suiza",
    "Brazil":"Brasil","Morocco":"Marruecos","Haiti":"Haití","Scotland":"Escocia","Australia":"Australia",
    "Türkiye":"Turquía","Turkey":"Turquía","Germany":"Alemania","Curaçao":"Curazao","Curacao":"Curazao",
    "Netherlands":"Países Bajos","Japan":"Japón","Ivory Coast":"C. de Marfil","Cote d'Ivoire":"C. de Marfil",
    "Ecuador":"Ecuador","Sweden":"Suecia","Tunisia":"Túnez","Spain":"España","Cape Verde":"Cabo Verde",
    "Belgium":"Bélgica","Egypt":"Egipto","Saudi Arabia":"Arabia Saudita","Uruguay":"Uruguay","Iran":"Irán",
    "New Zealand":"N. Zelanda","France":"Francia","Senegal":"Senegal","Iraq":"Iraq","Norway":"Noruega",
    "Algeria":"Argelia","Argentina":"Argentina","Austria":"Austria","Jordan":"Jordania","Portugal":"Portugal",
    "England":"Inglaterra","Croatia":"Croacia","Ghana":"Ghana","Panama":"Panamá","Colombia":"Colombia",
    "DR Congo":"RD Congo","Congo DR":"RD Congo","Uzbekistan":"Uzbekistán",
}
by_teams = {(f["home"], f["away"]): f for f in fixtures if f["phase"] == "group"}

KO_POINTS = {"R32":10,"R16":15,"QF":20,"SF":25,"final":30,"third":30,"champion":35}
def sign(x): return (x>0)-(x<0)
def match_points(pred, actual):
    ph,pa=pred; ah,aa=actual
    if sign(ph-pa)!=sign(ah-aa): return 0
    return max(0, 10-(abs(ph-ah)+abs(pa-aa)))

def fetch_espn():
    url=("https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/"
         "scoreboard?dates=20260611-20260719&limit=200")
    req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def main():
    data=fetch_espn()
    # overlay scores onto fixtures
    for e in data.get("events", []):
        comp=e["competitions"][0]; st=comp["status"]["type"]["name"]
        cs=comp["competitors"]
        home=next((t for t in cs if t["homeAway"]=="home"),None)
        away=next((t for t in cs if t["homeAway"]=="away"),None)
        if not home or not away: continue
        try: hs,as_=int(home["score"]),int(away["score"])
        except: continue
        eh=ESPN_TO_ES.get(home["team"]["displayName"],home["team"]["displayName"])
        ea=ESPN_TO_ES.get(away["team"]["displayName"],away["team"]["displayName"])
        f=by_teams.get((eh,ea)) or by_teams.get((ea,eh))
        if not f: continue
        if eh==f["away"]: hs,as_=as_,hs
        if st=="STATUS_FULL_TIME":
            f["home_score"],f["away_score"],f["status"]=hs,as_,"final"
        elif st in ("STATUS_IN_PROGRESS","STATUS_FIRST_HALF","STATUS_SECOND_HALF","STATUS_HALFTIME"):
            if f.get("status")!="final":
                f["home_score"],f["away_score"],f["status"]=hs,as_,"live"

    # group standings
    def group_standings():
        tbl={}
        for f in fixtures:
            if f["phase"]!="group": continue
            g=f["group"]; tbl.setdefault(g,{})
            for t in (f["home"],f["away"]):
                tbl[g].setdefault(t,{"team":t,"P":0,"W":0,"D":0,"L":0,"GF":0,"GA":0,"Pts":0})
            if f.get("status") in ("final","live") and f.get("home_score") is not None:
                h,a=f["home_score"],f["away_score"]; H=tbl[g][f["home"]]; A=tbl[g][f["away"]]
                H["P"]+=1;A["P"]+=1;H["GF"]+=h;H["GA"]+=a;A["GF"]+=a;A["GA"]+=h
                if h>a:H["W"]+=1;A["L"]+=1;H["Pts"]+=3
                elif h<a:A["W"]+=1;H["L"]+=1;A["Pts"]+=3
                else:H["D"]+=1;A["D"]+=1;H["Pts"]+=1;A["Pts"]+=1
        out={}
        for g,tm in tbl.items():
            rows=list(tm.values())
            for r in rows: r["GD"]=r["GF"]-r["GA"]
            rows.sort(key=lambda r:(-r["Pts"],-r["GD"],-r["GF"],r["team"]))
            out[g]=rows
        return out

    byno={f["match_no"]:f for f in fixtures}
    standings=[]; detail={}
    for p in participants:
        pid=str(p["id"]); gp=gpred.get(pid,{})
        gtot=0; gdet={}; exact=0
        for k,pred in gp.items():
            f=byno.get(int(k))
            if not f or f["phase"]!="group": continue
            if f.get("status") in ("final","live") and f.get("home_score") is not None:
                pts=match_points((pred[0],pred[1]),(f["home_score"],f["away_score"]))
                gtot+=pts; gdet[int(k)]=pts
                if pts==10: exact+=1
        standings.append({"id":p["id"],"name":p["name"],"g":gtot,"k":0,"total":gtot,
                          "played":len(gdet),"exact":exact})
        detail[p["id"]]={"group":gdet,"groupPts":gtot,"koPts":0,"total":gtot,"exact":exact,"koDetail":{}}
    standings.sort(key=lambda r:(-r["total"],-r["exact"],r["name"]))
    rank=0; prev=None
    for i,r in enumerate(standings):
        key=(r["total"],r["exact"])
        if key!=prev: rank=i+1; prev=key
        r["rank"]=rank

    # compact fixtures (no static fields the shell already has): match_no, scores, status
    fx_dyn={}
    live_list=[]
    for f in fixtures:
        if f.get("status") in ("final","live") and f.get("home_score") is not None:
            fx_dyn[f["match_no"]]={"hs":f["home_score"],"as":f["away_score"],"st":f["status"]}
            if f["status"]=="live":
                live_list.append({"match_no":f["match_no"],"home":f["home"],"away":f["away"],
                                  "hs":f["home_score"],"as":f["away_score"]})
    finished=sum(1 for f in fixtures if f.get("status")=="final")
    now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-6)))
    out={"fxDyn":fx_dyn,"standings":standings,"detail":detail,"groups":group_standings(),
         "meta":{"finished":finished,"liveCount":len(live_list),"live":live_list,
                 "updatedTs":now.strftime("%d/%m/%Y %H:%M"),"updatedISO":now.isoformat()}}
    json.dump(out, open(os.path.join(ROOT,"data.json"),"w"), ensure_ascii=False)
    print(f"wrote data.json: finished={finished} live={len(live_list)} leader={standings[0]['name']} ({standings[0]['total']})")

if __name__=="__main__":
    main()
