"use client";
import {useMemo,useState} from "react";
import type {CustomUniversity,Participant,UniversityCategory} from "../types";
import type {University} from "./UniversityAutocomplete";
import {type PendingUniversity,canonicalCategory,classifiedParticipants,classifyUniversity,normalizeUniversityKey,universityIdentity,UNIVERSITY_CATEGORIES} from "./universityClassification";

export function UniversityReview({people,directory,custom,pending=[],confirm}:{people:Participant[];directory:University[];custom:CustomUniversity[];pending?:PendingUniversity[];confirm:(entry:CustomUniversity)=>boolean}) {
  const entries=useMemo(()=>{
    const unique=new Map<string,{id:string;name:string;count:number;category?:UniversityCategory;aliases:string[]}>();
    for(const person of classifiedParticipants(people,directory,custom)){
      const name=String(person.attributes.University??"").trim(); if(!name)continue;
      const identity=universityIdentity(name,directory), existing=[...custom,...pending].find(item=>item.id===identity?.id || [item.name,...item.aliases].some(alias=>normalizeUniversityKey(alias)===normalizeUniversityKey(name)));
      const id=existing?.id??identity?.id??`custom:${normalizeUniversityKey(name)}`;
      const row=unique.get(id);
      if(row)row.count++;
      else unique.set(id,{id,name:identity?.official_english_name??existing?.name??name,count:1,category:classifyUniversity(name,directory,custom)??canonicalCategory(person.attributes["University Category"]),aliases:existing?.aliases??[]});
    }
    return [...unique.values()].sort((a,b)=>Number(Boolean(a.category))-Number(Boolean(b.category))||a.name.localeCompare(b.name));
  },[people,directory,custom,pending]);
  const unresolved=entries.filter(item=>!item.category);
  return <section className="card mt-5 p-5" aria-label="University classification review">
    <h2 className="text-lg font-extrabold">{unresolved.length ? "University classification required" : "University classifications"}</h2>
    <p className="mt-1 text-sm text-slate-500">{unresolved.length ? `Confirm ${unresolved.length} unique ${unresolved.length===1?"university":"universities"} before generating allocations. No category is guessed.` : "Review the Public/Private grouping categories and correct them when necessary."} Grouping categories do not change an institution’s legal status. Confirmed corrections are reusable on this computer; export the directory to move them to another computer.</p>
    <div className="mt-3 divide-y">{entries.map(item=><UniversityReviewRow key={`${item.id}:${item.category??"unresolved"}:${item.aliases.join(",")}`} entry={item} confirm={confirm}/>)}</div>
  </section>;
}
function UniversityReviewRow({entry,confirm}:{entry:{id:string;name:string;count:number;category?:UniversityCategory;aliases:string[]};confirm:(entry:CustomUniversity)=>boolean}) {
  const [editing,setEditing]=useState(!entry.category),[category,setCategory]=useState<UniversityCategory|"">(entry.category??""),[aliases,setAliases]=useState(entry.aliases.join(", "));
  return <div className="flex flex-wrap items-center gap-3 py-3 text-sm">
    <span className="min-w-44 flex-1"><b>{entry.name}</b><span className="ml-2 text-xs text-slate-500">{entry.count} {entry.count===1?"new hire":"new hires"}</span></span>
    {editing ? <>
      <select aria-label={`Category for ${entry.name}`} className="input w-auto" value={category} onChange={e=>setCategory(e.target.value as UniversityCategory)}><option value="">Choose category</option>{Object.entries(UNIVERSITY_CATEGORIES).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select>
      <input className="input w-full sm:w-64" aria-label={`Aliases for ${entry.name}`} placeholder="Aliases, separated by commas" value={aliases} onChange={e=>setAliases(e.target.value)}/>
      <button className="btn btn-primary" disabled={!category} onClick={()=>{if(!category)return;if(confirm({id:entry.id,name:entry.name,aliases:aliases.split(",").map(value=>value.trim()).filter(Boolean),category}))setEditing(false)}}>Confirm</button>
    </> : <><span className="text-slate-600">{entry.category&&UNIVERSITY_CATEGORIES[entry.category]}</span><button className="text-sm font-bold text-sky" onClick={()=>setEditing(true)}>Correct</button></>}
  </div>;
}
