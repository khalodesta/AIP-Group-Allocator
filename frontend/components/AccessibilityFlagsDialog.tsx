"use client";

import {useEffect, useRef, useState} from "react";
import {Accessibility, Search} from "lucide-react";
import type {Participant} from "../types";

export function AccessibilityFlagsDialog({people, savedIds, save, cancel}:{
  people:Participant[]; savedIds:string[]; save:(ids:string[])=>void; cancel:()=>void;
}) {
  const dialog=useRef<HTMLDialogElement>(null);
  const [search,setSearch]=useState("");
  const [selected,setSelected]=useState(()=>new Set(savedIds));
  useEffect(()=>{
    const element=dialog.current;
    element?.showModal();
    return ()=>element?.close();
  },[]);
  const query=search.trim().toLocaleLowerCase();
  const visible=people.filter(person=>`${person.name} ${person.attributes.University??""}`.toLocaleLowerCase().includes(query));
  return <dialog ref={dialog} className="accessibility-dialog" aria-labelledby="accessibility-title" aria-describedby="accessibility-description" onCancel={event=>{event.preventDefault();cancel();}}>
    <div className="accessibility-dialog-heading"><Accessibility size={20} aria-hidden="true"/><h2 id="accessibility-title">Accessibility Flags</h2></div>
    <p id="accessibility-description">Select new hires with a confirmed disability status. These indicators are for administrative awareness only and do not affect allocations.</p>
    <label className="accessibility-search"><Search size={16} aria-hidden="true"/><input type="search" aria-label="Search new hires" placeholder="Search name or university" value={search} onChange={event=>setSearch(event.target.value)}/></label>
    <div className="accessibility-people" aria-label="New hires">
      {visible.map(person=><label className="accessibility-person" key={person.id}>
        <input type="checkbox" checked={selected.has(person.id)} onChange={event=>{const checked=event.target.checked;setSelected(current=>{const next=new Set(current);if(checked)next.add(person.id);else next.delete(person.id);return next;});}}/>
        <span><b>{person.name.trim()||"Unnamed new hire"}</b><span>{String(person.attributes.University??"").trim()||"University not provided"}</span></span>
      </label>)}
      {!visible.length&&<p className="accessibility-empty">No new hires match your search.</p>}
    </div>
    <footer><span role="status">{people.filter(person=>selected.has(person.id)).length} selected</span><div><button className="btn btn-outline" onClick={cancel}>Cancel</button><button className="btn btn-primary" onClick={()=>save(people.filter(person=>selected.has(person.id)).map(person=>person.id))}>Save Flags</button></div></footer>
  </dialog>;
}
