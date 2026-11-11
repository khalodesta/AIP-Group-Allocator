import type { Participant, SupportMember, UniversityCategory } from "../types";
import { UNIVERSITY_CATEGORIES } from "./universityClassification";
import {Accessibility} from "lucide-react";

export function genderRowClass(gender: unknown): string {
  return gender === "Male" ? "result-gender-male" : gender === "Female" ? "result-gender-female" : "result-gender-neutral";
}
export function hotelRoomAppearance(ids: string[], people: Record<string, Participant>, support: Record<string, SupportMember>) {
  if(!ids.length)return {className:"hotel-room-neutral",warning:""};
  const genders=ids.map(id=>people[id]?.attributes.Gender ?? support[id]?.gender);
  if (genders.length && genders.every(gender=>gender==="Male")) return {className:"hotel-room-male",warning:""};
  if (genders.length && genders.every(gender=>gender==="Female")) return {className:"hotel-room-female",warning:""};
  const mixed=genders.includes("Male")&&genders.includes("Female");
  return {className:"hotel-room-neutral",warning:mixed ? "Mixed-gender room: review the approved manual exception." : "Gender is not recorded for every occupant; this room has a neutral appearance."};
}
export function ParticipantIdentity({name,gender,category,role,accessibilityFlag=false}:{name:string;gender?:unknown;category?:UniversityCategory;role?:string;accessibilityFlag?:boolean}) {
  const recordedGender=gender==="Male"||gender==="Female"?gender:undefined;
  return <span className="participant-identity">
    <span className="participant-name-line"><span className="person-name" role={recordedGender?"group":undefined} tabIndex={recordedGender?0:undefined} title={recordedGender ? `Gender: ${recordedGender}` : undefined} aria-label={recordedGender ? `${name}; Gender: ${recordedGender}` : name}>{name}</span><UniversityCategoryIndicator category={category}/>{accessibilityFlag&&<span className="accessibility-indicator" role="img" tabIndex={0} title="Disability indicator — administrative awareness only" aria-label="Disability indicator — administrative awareness only"><Accessibility size={13} strokeWidth={1.7} aria-hidden="true"/></span>}</span>
    {role && <span className={`result-role ${role==="Support Lead"?"result-role-lead":""}`}>{role}</span>}
  </span>;
}
export function UniversityCategoryIndicator({category}:{category?:UniversityCategory}) {
  if(category!=="public"&&category!=="private")return null;
  const label=`University category: ${UNIVERSITY_CATEGORIES[category]}`;
  return <span className={`university-marker university-${category}`} role="img" tabIndex={0} title={label} aria-label={label}/>;
}
export function ResultsLegend() {
  return <aside aria-label="Results color legend" className="results-legend">
    <span className="legend-item" title="Light blue rows indicate recorded Male gender" aria-label="Male rows"><span className="legend-gender legend-male" aria-hidden="true"/>Male</span>
    <span className="legend-item" title="Light rose rows indicate recorded Female gender" aria-label="Female rows"><span className="legend-gender legend-female" aria-hidden="true"/>Female</span>
    <span className="legend-divider" aria-hidden="true"/>
    {Object.entries(UNIVERSITY_CATEGORIES).map(([category,label])=><span key={category} className="legend-item" title={`${label} university`}><span aria-hidden="true" className={`university-marker university-${category}`}/>{label}</span>)}
    <span className="sr-only">Row color indicates recorded gender. The marker indicates the university grouping category. Each person's recorded attributes are available on focus or hover.</span>
  </aside>;
}
