import type {Allocation} from "../types";

export const MANUAL_ROOM_PREFIX="hotel-manual-";
export const isManualRoom=(id:string)=>id.startsWith(MANUAL_ROOM_PREFIX);

export function nextRoomNumber(allocation:Allocation, previousNumber=0):number {
  const hotel=allocation.activities.find(activity=>activity.activity_id==="hotel");
  return Math.max(previousNumber,0,...(hotel?.groups.map(room=>Number(room.name.match(/^Room\s+(\d+)\b/i)?.[1]??0))??[]))+1;
}

export function addHotelRoom(allocation:Allocation, id:string, number:number):Allocation {
  if(!isManualRoom(id)||allocation.activities.some(activity=>activity.groups.some(group=>group.id===id)))throw new Error("Room identifiers must be unique.");
  return {...allocation,activities:allocation.activities.map(activity=>activity.activity_id!=="hotel"?activity:{...activity,groups:[...activity.groups,{id,name:`Room ${number}`,participant_ids:[]}]})};
}

export function removeEmptyHotelRoom(allocation:Allocation, id:string):Allocation {
  const room=allocation.activities.find(activity=>activity.activity_id==="hotel")?.groups.find(group=>group.id===id);
  if(!room||!isManualRoom(id)||room.participant_ids.length)throw new Error("Only an empty manually added room can be removed.");
  return {...allocation,activities:allocation.activities.map(activity=>activity.activity_id!=="hotel"?activity:{...activity,groups:activity.groups.filter(group=>group.id!==id)})};
}

export function withoutEmptyHotelRooms(allocation:Allocation):Allocation {
  return {...allocation,activities:allocation.activities.map(activity=>activity.activity_id!=="hotel"?activity:{...activity,groups:activity.groups.filter(room=>room.participant_ids.length>0)})};
}

export function resetHotelToGenerated(draft:Allocation, generated:Allocation):Allocation {
  const hotel=generated.activities.find(activity=>activity.activity_id==="hotel");
  if(!hotel)return draft;
  return {...draft,activities:draft.activities.map(activity=>activity.activity_id==="hotel"?structuredClone(hotel):activity)};
}
