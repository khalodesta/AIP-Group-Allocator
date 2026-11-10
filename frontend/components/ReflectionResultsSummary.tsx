import type {Allocation} from "../types";
import {Clock3, Users} from "lucide-react";
import {latestAppointmentEnd} from "./reflectionUi";
export function ReflectionResultsSummary({activity}:{activity:Allocation["activities"][number]}) {
  const sessions=activity.sessions??[];
  return <div aria-label="My Reflections statistics" className="reflection-results-summary">
    <div className="reflection-stat"><span className="stat-symbol" aria-hidden="true"><Users size={18}/></span><div><p className="text-xs result-stat-label">Participants</p><p className="result-stat-value">{sessions.length||activity.groups.reduce((count,group)=>count+group.participant_ids.length,0)}</p></div></div>
    <div className="reflection-stat"><span className="stat-symbol" aria-hidden="true"><Clock3 size={18}/></span><div><p className="text-xs result-stat-label">Completion Time</p><p className="result-stat-value">{latestAppointmentEnd(sessions)}</p></div></div>
  </div>;
}
