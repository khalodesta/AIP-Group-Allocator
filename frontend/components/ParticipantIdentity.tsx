import type { UniversityCategory } from "../types";
import { UNIVERSITY_CATEGORIES } from "./universityClassification";

export function ParticipantIdentity({name,gender,category,role}:{name:string;gender?:unknown;category?:UniversityCategory;role?:string}) {
  const recordedGender=gender==="Male"||gender==="Female"?gender:undefined;
  return <span className="inline-flex min-w-0 flex-wrap items-center gap-2">
    <span className={`person-name person-gender-${recordedGender?.toLowerCase() ?? "unknown"}`} role={recordedGender?"group":undefined} tabIndex={recordedGender?0:undefined} title={recordedGender ? `Gender: ${recordedGender}` : undefined} aria-label={recordedGender ? `${name}; Gender: ${recordedGender}` : name}>{name}</span>
    {category && <span className={`university-marker university-${category}`} role="img" tabIndex={0} title={`University category: ${UNIVERSITY_CATEGORIES[category]}`} aria-label={`University category: ${UNIVERSITY_CATEGORIES[category]}`} />}
    {role && <span className="rounded bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">{role}</span>}
  </span>;
}
export function ResultsLegend() {
  return <aside aria-label="Results color legend" className="card mb-4 flex flex-wrap items-center gap-x-5 gap-y-2 p-4 text-xs text-slate-600">
    <b className="text-navy">Color guide</b>
    <span className="inline-flex gap-2"><span className="person-name person-gender-male">Male</span><span className="person-name person-gender-female">Female</span></span>
    {Object.entries(UNIVERSITY_CATEGORIES).map(([category,label])=><span key={category} className="inline-flex items-center gap-1.5"><span aria-hidden="true" className={`university-marker university-${category}`}/>{label}</span>)}
    <span className="text-slate-500">Hover or focus on a name or marker for recorded attributes.</span>
  </aside>;
}
