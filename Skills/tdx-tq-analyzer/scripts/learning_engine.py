# -*- coding: utf-8 -*-
"""Deterministic learning scheduler for tdx-tq-analyzer. Standard library only."""
import argparse, json, random
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRICULUM = ROOT / "learning" / "curriculum.json"
DEFAULT_STATE = ROOT / "state" / "learning_progress.json"

def load_curriculum(path=CURRICULUM):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    ids=[x[0] for c in data["chapters"] for x in c["lessons"]]
    if len(ids)!=len(set(ids)): raise ValueError("duplicate lesson id")
    return data

def fresh_state():
    return {"schema_version":1,"updated_at":None,"lesson_progress":{},"reviews":[],"daily_history":[]}

def load_state(path=DEFAULT_STATE):
    p=Path(path)
    if not p.exists(): return fresh_state()
    data=json.loads(p.read_text(encoding="utf-8"))
    if data.get("schema_version")!=1: raise ValueError("unsupported progress schema")
    data.setdefault("lesson_progress",{}); data.setdefault("reviews",[]); data.setdefault("daily_history",[])
    return data

def save_state(state,path=DEFAULT_STATE):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    state["updated_at"]=datetime.now().isoformat(timespec="seconds")
    tmp=p.with_suffix(p.suffix+".tmp")
    tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8")
    tmp.replace(p)

def all_lessons(curriculum):
    out=[]
    for ch in curriculum["chapters"]:
        for row in ch["lessons"]:
            out.append({"id":row[0],"title":row[1],"objective":row[2],"prerequisite":row[3],"teaching":row[4],"chapter_id":ch["id"],"chapter_title":ch["title"],"status":ch["status"]})
    return out

def due_reviews(state, today):
    due=[]
    for lid,p in state["lesson_progress"].items():
        due_on=p.get("due_date")
        if due_on and due_on<=today.isoformat(): due.append((due_on,lid,p))
    return sorted(due,key=lambda x:(x[0],x[1]))

def build_daily_plan(curriculum,state,today=None):
    today=today or date.today()
    lessons=all_lessons(curriculum); by_id={x["id"]:x for x in lessons}
    reviews=due_reviews(state,today)
    review_items=[by_id[x[1]] for x in reviews if x[1] in by_id][:3]
    completed={k for k,v in state["lesson_progress"].items() if v.get("mastery",0)>=0.8}
    mvp=[x for x in lessons if x["status"]=="mvp"]
    new_lesson=next((x for x in mvp if x["id"] not in completed),None)
    # deterministic daily image prompt: rotate only among studied/available concepts
    image_pool=[x for x in lessons if x["status"]=="mvp"]
    day_index=today.toordinal()
    image_lesson=image_pool[day_index % len(image_pool)] if image_pool else None
    return {"date":today.isoformat(),"minutes":curriculum.get("daily_minutes",18),
      "reviews":review_items,"new_lesson":new_lesson,"daily_image":image_lesson,
      "exercise_count":3 if new_lesson else 5,
      "completed_count":len(completed),"total_mvp":len(mvp)}

def record_result(state,lesson_id,correct,total,quality=3,today=None):
    today=today or date.today()
    if total<=0 or correct<0 or correct>total: raise ValueError("invalid score")
    p=state["lesson_progress"].setdefault(lesson_id,{"attempts":0,"correct":0,"mastery":0.0,"interval_days":0,"due_date":None})
    p["attempts"]+=1; p["correct"]+=correct
    accuracy=correct/total
    # Conservative mastery: accumulated accuracy + explanation quality + recency interval.
    p["last_accuracy"]=round(accuracy,4); p["last_quality"]=int(max(0,min(5,quality)))
    old=float(p.get("mastery",0))
    p["mastery"]=round(min(1.0,0.65*old+0.25*accuracy+0.10*(quality/5)),4)
    if accuracy>=0.9 and quality>=4: interval=max(1,int(p.get("interval_days",0))*2 or 1)
    elif accuracy>=0.7: interval=max(1,int(p.get("interval_days",0)) or 1)
    else: interval=1
    p["interval_days"]=min(interval,30)
    p["last_seen"]=today.isoformat()
    p["due_date"]=(today+timedelta(days=p["interval_days"])).isoformat()
    state["reviews"].append({"date":today.isoformat(),"lesson_id":lesson_id,"correct":correct,"total":total,"quality":quality,"mastery":p["mastery"]})
    return p

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--state",default=str(DEFAULT_STATE)); ap.add_argument("--date",default=None)
    ap.add_argument("--record",nargs=3,metavar=("LESSON_ID","CORRECT","TOTAL"))
    ap.add_argument("--quality",type=int,default=3); ap.add_argument("--print-plan",action="store_true")
    a=ap.parse_args(); c=load_curriculum(); s=load_state(a.state)
    today=date.fromisoformat(a.date) if a.date else date.today()
    if a.record:
        record_result(s,a.record[0],int(a.record[1]),int(a.record[2]),a.quality,today); save_state(s,a.state)
    plan=build_daily_plan(c,s,today)
    if a.print_plan or a.record: print(json.dumps(plan,ensure_ascii=False,indent=2))
if __name__=="__main__": main()
