import type {FacultyMember,Group,Participant,SupportMember} from "../types";
export function hotelRoomSummary(groups:Group[],people:Record<string,Participant>,support:Record<string,SupportMember>,faculty:FacultyMember[]) {
  const counts={total_rooms:new Set(groups.map(group=>group.id)).size,new_hire_shared:0,new_hire_analyst_shared:0,new_hire_single:0,support_lead_single:0,analyst_support_single:0,faculty_single:0};
  let otherSharedRooms=0;
  const facultyIds=new Set(faculty.map(member=>member.id));
  for(const room of groups){
    const ids=room.participant_ids;
    if(ids.length===2){if(ids.every(id=>people[id]))counts.new_hire_shared++;else if(ids.some(id=>people[id])&&ids.some(id=>support[id]?.category==="Analyst Support"))counts.new_hire_analyst_shared++;else otherSharedRooms++;}
    else if(ids.length===1){const id=ids[0];if(people[id])counts.new_hire_single++;else if(facultyIds.has(id))counts.faculty_single++;else if(support[id]?.category==="Support Lead")counts.support_lead_single++;else if(support[id]?.category==="Analyst Support")counts.analyst_support_single++;}
    else otherSharedRooms++;
  }
  return {...counts,...(otherSharedRooms?{other_shared_rooms:otherSharedRooms}:{})};
}
