import type {Participant,ReflectionSession} from "../types";
export function eligiblePrayerParticipants(people:Participant[]) {
  return people.filter(person=>person.attributes.Gender==="Male");
}
export function prunePrayerSelection(ids:string[],people:Participant[]) {
  const eligible=new Set(eligiblePrayerParticipants(people).map(person=>person.id));
  return [...new Set(ids.filter(id=>eligible.has(id)))];
}
export function appointmentMinutes(value:string) {
  const clock=value.match(/^(\d{1,2}):(\d{2})(?:\s*(AM|PM))?$/i);
  if (!clock) return -1;
  let hour=Number(clock[1]);
  if(clock[3]){hour%=12;if(clock[3].toUpperCase()==="PM")hour+=12;}
  return hour*60+Number(clock[2]);
}
export function latestAppointmentEnd(sessions:ReflectionSession[]) {
  return sessions.reduce<ReflectionSession|undefined>((latest,session)=>!latest||appointmentMinutes(session.end_time)>appointmentMinutes(latest.end_time)?session:latest,undefined)?.end_time??"—";
}
