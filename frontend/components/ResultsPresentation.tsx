import type {ReactNode} from "react";
import {BedDouble, CalendarClock, Check, ShieldCheck, Users} from "lucide-react";
import type {Participant, UniversityCategory} from "../types";
import {ParticipantIdentity} from "./ParticipantIdentity";

export function ParticipantRow({index,name,gender,category,role,person,offering,chemistryEnabled,selected=false,accessibilityFlag=false}:{
  index:number;name:string;gender?:unknown;category?:UniversityCategory;role?:string;
  person?:Participant;offering?:string;chemistryEnabled:boolean;selected?:boolean;accessibilityFlag?:boolean;
}) {
  const primary=String(person?.attributes["Primary Chemistry"]??"").trim();
  const secondary=String(person?.attributes["Secondary Chemistry"]??"").trim();
  return <div className="participant-record-content">
    <span className="participant-number" aria-label={`Participant ${index}`}>{String(index).padStart(2,"0")}</span>
    <div className="participant-record-body">
      <div className="participant-primary-line">
        <ParticipantIdentity name={name} gender={gender} category={category} role={role} accessibilityFlag={Boolean(person&&accessibilityFlag)}/>
        {selected&&<span className="participant-selected-label" title="Selected for switching"><Check size={13} aria-hidden="true"/><span className="sr-only">Selected for switching</span></span>}
      </div>
      {person&&<>
        <p className="participant-university">{String(person.attributes.University??"").trim()||"University not provided"}</p>
        <div className="participant-metadata">
          <span className="participant-offering" title="L3 Offering">{offering||"Offering not provided"}</span>
          {chemistryEnabled&&(primary&&secondary?<>
            <span className="chemistry-segment" title={`Primary Business Chemistry: ${primary}`}><span>Primary</span> {primary}</span>
            <span className="chemistry-segment" title={`Secondary Business Chemistry: ${secondary}`}><span>Secondary</span> {secondary}</span>
          </>:<span className="metadata-warning">Business Chemistry information is incomplete</span>)}
        </div>
      </>}
    </div>
  </div>;
}

export function AllocationGroupCard({title,count,index,activityId,room,children}:{
  title:string;count:number;index:number;activityId:string;
  room?:{className:string;warning:string}|null;children:ReactNode;
}) {
  const roomTitle=room?title.replace(/\s*[—–-]\s*Single Occupancy\s*$/i,""):title;
  const mixedRoom=Boolean(room?.warning.startsWith("Mixed-gender"));
  return <article data-room-gender={room?.className.replace("hotel-room-","")} className={`allocation-group-card ${room?`hotel-room ${room.className}`:""}`}>
    <header className="allocation-card-header">
      <span className={`allocation-card-symbol ${room?"room-symbol":""}`} aria-hidden="true">{room?<BedDouble size={18}/>:String(index).padStart(2,"0")}</span>
      <div className="allocation-card-heading"><h3>{roomTitle}</h3><p>{room?`${count===0?"Empty room":count===1?"Single occupancy":"Shared room"} · ${count} ${count===1?"occupant":"occupants"}`:`${count} ${activityId==="reflection"?"appointments":"participants"}`}</p>{room?.warning&&!mixedRoom&&<span className="room-neutral-caption" title={room.warning}>Gender not recorded</span>}</div>
    </header>
    {mixedRoom&&<p className="room-notice" role="note"><ShieldCheck size={14} aria-hidden="true"/>{room?.warning}</p>}
    {children}
  </article>;
}

export function ResultSectionHeader({title,activityId,groups}:{title:string;activityId:string;groups:number}) {
  const descriptions:Record<string,string>={main:"Your permanent onboarding groups.",quiz:"Fresh teams for a shared challenge.",team:"A new mix of colleagues to collaborate with.",bus:"New hires and support, coordinated across two buses.",reflection:"One-to-one appointments with your faculty.",hotel:"A private accommodation manifest for every attendee."};
  return <div className="result-section-header"><div><h2>{title}</h2><p>{descriptions[activityId]??"Review the current participant assignments."}</p></div>{activityId!=="reflection"&&<span className="result-section-count">{activityId==="hotel"?<BedDouble size={15} aria-hidden="true"/>:<Users size={15} aria-hidden="true"/>}{groups} {activityId==="hotel"?"rooms":activityId==="bus"?"buses":"groups"}</span>}</div>;
}

export function HotelResultsSummary({summary}:{summary:Record<string,number>}) {
  const breakdown:[string,string][]=[
    ["new_hire_shared","New-hire shared"],["new_hire_analyst_shared","New hire + Analyst Support"],
    ["new_hire_single","Single new hires"],["support_lead_single","Single Support Leads"],
    ["analyst_support_single","Single Analyst Support"],["faculty_single","Single faculty"],
  ];
  if(summary.other_shared_rooms)breakdown.push(["other_shared_rooms","Approved manual arrangements"]);
  return <section className="hotel-results-summary" aria-label="Hotel occupancy summary"><div className="hotel-total"><span className="result-eyebrow">Accommodation</span><div><strong>{summary.total_rooms}</strong><span>Total rooms required</span></div><span className="hotel-private-label"><ShieldCheck size={12} aria-hidden="true"/>Private manifest</span></div><dl className="hotel-summary-breakdown">{breakdown.map(([key,label])=><div key={key}><dt>{label}</dt><dd>{summary[key]??0}</dd></div>)}</dl></section>;
}

export function FacultyScheduleHeader({name}:{name:string}) {
  return <header className="faculty-schedule-header"><span className="allocation-card-symbol" aria-hidden="true"><CalendarClock size={18}/></span><h3>{name}</h3></header>;
}
