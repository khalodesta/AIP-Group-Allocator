"use client";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import {
  DndContext,
  DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronDown,
  Download,
  FileSpreadsheet,
  Plus,
  RefreshCw,
  Sparkles,
  Trash2,
  UploadCloud,
  Users,
  BedDouble,
  Bus,
  CalendarClock,
  GripVertical,
  LayoutGrid,
  PencilLine,
  Puzzle,
  RotateCcw,
  Trophy,
  Undo2,
} from "lucide-react";
import { API, download, jsonApi } from "@/lib/api";
import type {
  Allocation,
  ChemistryRecord,
  Configuration,
  CustomUniversity,
  FacultyMember,
  Metrics,
  Participant,
  SupportMember,
} from "@/types";
import {
  UniversityAutocomplete,
  type University,
} from "@/components/UniversityAutocomplete";
import { toast } from "sonner";
import {genderRowClass,hotelRoomAppearance,ParticipantIdentity, ResultsLegend} from "@/components/ParticipantIdentity";
import {UniversityReview} from "@/components/UniversityReview";
import {canonicalCategory,classifiedParticipants,mergedUniversityDirectory,migrateCustomDirectory,parseCustomDirectory,universityIdentity,type PendingUniversity} from "@/components/universityClassification";
import {hotelRoomSummary} from "@/components/hotelSummary";
import {eligiblePrayerParticipants,prunePrayerSelection} from "@/components/reflectionUi";
import {ReflectionResultsSummary as ReflectionSummary} from "@/components/ReflectionResultsSummary";
import {AllocationGroupCard,FacultyScheduleHeader,HotelResultsSummary,ParticipantRow,ResultSectionHeader} from "@/components/ResultsPresentation";
const CUSTOM_DIRECTORY_KEY="aip-university-directory-v1";

type Step = "data" | "team" | "sizes" | "results";
const steps: { id: Step; label: string }[] = [
  { id: "data", label: "Upload Data" },
  { id: "team", label: "Faculty & Support" },
  { id: "sizes", label: "Group Sizes" },
  { id: "results", label: "Results" },
];
const activities = [
  { id: "main", name: "Main Groups", value: 6 },
  { id: "quiz", name: "Quiz Night", value: 6 },
  { id: "team", name: "Team Building", value: 6 },
];
const resultActivityIcons:Record<string,typeof Users>={main:LayoutGrid,quiz:Trophy,team:Puzzle,bus:Bus,reflection:CalendarClock,hotel:BedDouble};
const OFFERINGS = [
  "AI & Data",
  "Customer",
  "ET&P",
  "Engineering",
  "Cyber",
] as const;
const standardOffering = (value: unknown) => {
  const raw = String(value ?? "").trim(),
    key = raw
      .toLocaleLowerCase()
      .replace(/&/g, " and ")
      .replace(/[^a-z0-9]+/g, " ")
      .trim();
  if (["ai data", "ai and data", "data ai", "data and ai"].includes(key))
    return "AI & Data";
  if (["et p", "et and p", "etp"].includes(key)) return "ET&P";
  return (
    OFFERINGS.find((x) => x.toLocaleLowerCase() === raw.toLocaleLowerCase()) ??
    raw
  );
};
const initialConfig: Configuration = {
  schema_version: 2,
  activities: activities.map((x) => ({
    ...x,
    mode: "max_size",
    locked: false,
  })),
  factors: [],
  custom_universities: [],
  seed: 42,
  time_limit_seconds: 20,
  repeat_weight: 1,
  include_business_chemistry: true,
  allow_accommodation_policy_overrides: false,
  reflection_settings: {
    enabled: false,
    selected_participant_ids: [],
    start_time: "11:00",
    session_duration_minutes: 20,
    prayer_deadline: "12:00",
    resume_time: "13:00",
    end_time: null,
  },
};
const uid = (prefix: string) => `${prefix}-${crypto.randomUUID().slice(0, 8)}`;
const blankPerson = (): Participant => ({
  id: uid("P"),
  name: "",
  attributes: { Gender: "", University: "", "L3 Offering": "" },
});
type EditConflict = {
  rule: string;
  message: string;
  policy_sensitive: boolean;
  overridable: boolean;
  participant_ids: string[];
};
type ManualOverride = {
  id: string;
  activity: string;
  participantIds: string[];
  rule: string;
  message: string;
  timestamp: string;
  active: boolean;
  policySensitive: boolean;
};
type PendingEdit = {
  participantId: string;
  targetGroupId: string;
  swapWithId?: string;
  conflicts: EditConflict[];
};

export default function Home() {
  const [step, setStep] = useState<Step>("data"),
    [participants, setParticipants] = useState<Participant[]>([]),
    [chemistry, setChemistry] = useState<ChemistryRecord[]>([]),
    [review, setReview] = useState<ChemistryRecord[]>([]),
    [showManual, setShowManual] = useState(false),
    [manualDraft, setManualDraft] = useState("25"),
    [faculty, setFaculty] = useState<FacultyMember[]>(() =>
      [1, 2, 3].map((i) => ({ id: `faculty-${i}`, name: "", offering: "" })),
    ),
    [support, setSupport] = useState<SupportMember[]>([]),
    [supportDraft, setSupportDraft] = useState("0"),
    [config, setConfig] = useState(initialConfig),
    [allocation, setAllocation] = useState<Allocation | null>(null),
    [generated, setGenerated] = useState<Allocation | null>(null),
    [metrics, setMetrics] = useState<Metrics | null>(null),
    [tab, setTab] = useState("main"),
    [loading, setLoading] = useState(false),
    [error, setError] = useState(""),
    [success, setSuccess] = useState(""),
    [scheduleExtension,setScheduleExtension]=useState<string|null>(null),
    [universities, setUniversities] = useState<University[]>([]),
    [pendingUniversityReview,setPendingUniversityReview]=useState<PendingUniversity[]>([]),
    [editMode, setEditMode] = useState(false),
    [editDraft, setEditDraft] = useState<Allocation | null>(null),
    [undoStack, setUndoStack] = useState<Allocation[]>([]),
    [swapA, setSwapA] = useState(""),
    [swapB, setSwapB] = useState(""),
    [individualOpen, setIndividualOpen] = useState(false),
    [overrides, setOverrides] = useState<ManualOverride[]>([]),
    [draftOverrides, setDraftOverrides] = useState<ManualOverride[]>([]),
    [pendingEdit, setPendingEdit] = useState<PendingEdit | null>(null),
    [showOverrides, setShowOverrides] = useState(false),
    [pendingExport, setPendingExport] = useState<null | (() => void)>(null);
  const masterInput = useRef<HTMLInputElement>(null),
    chemInput = useRef<HTMLInputElement>(null),
    supportInput = useRef<HTMLInputElement>(null),
    directoryInput = useRef<HTMLInputElement>(null);
  const customUniversities=config.custom_universities??[];
  const allUniversities=useMemo(()=>mergedUniversityDirectory(universities,customUniversities,pendingUniversityReview),[universities,customUniversities,pendingUniversityReview]);
  const normalizedParticipants=useMemo(()=>classifiedParticipants(participants,allUniversities,customUniversities),[participants,allUniversities,customUniversities]);
  const unresolvedUniversities=normalizedParticipants.filter(person=>!person.attributes["University Category"]);
  const pmap = useMemo(
    () => Object.fromEntries(normalizedParticipants.map((p) => [p.id, p])),
    [normalizedParticipants],
  );
  const smap = useMemo(
    () => Object.fromEntries(support.map((p) => [p.id, p])),
    [support],
  );
  const displayedAllocation = editMode && editDraft ? editDraft : allocation;
  const current = displayedAllocation?.activities.find(
    (a) => a.activity_id === tab,
  );
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(TouchSensor),
    useSensor(KeyboardSensor),
  );
  const chemistryEnabled = config.include_business_chemistry === true;
  const reflectionSettings =
    config.reflection_settings ?? initialConfig.reflection_settings;
  useEffect(()=>{
    try {
      const saved=localStorage.getItem(CUSTOM_DIRECTORY_KEY);
      if(saved){
        const migrated=migrateCustomDirectory(JSON.parse(saved));
        setConfig(c=>({...c,custom_universities:migrated.universities}));
        setPendingUniversityReview(migrated.pending);
        localStorage.setItem(CUSTOM_DIRECTORY_KEY,JSON.stringify({schema_version:2,universities:migrated.universities,pending_review:migrated.pending}));
      }
    }
    catch {setError("Saved university corrections could not be loaded. Import a valid directory or confirm classifications again.");}
  },[]);
  useEffect(()=>{
    setConfig(current=>{
      const settings=current.reflection_settings??initialConfig.reflection_settings;
      const selected=prunePrayerSelection(settings.selected_participant_ids,participants);
      if(selected.length===settings.selected_participant_ids.length&&selected.every((id,index)=>id===settings.selected_participant_ids[index]))return current;
      return {...current,reflection_settings:{...settings,selected_participant_ids:selected}};
    });
  },[participants]);
  useEffect(() => {
    jsonApi("/api/universities")
      .then((x) => setUniversities(x.universities))
      .catch(() => setError("University directory could not be loaded."));
  }, []);
  useEffect(() => {
    if (error) {
      toast.error(error, { id: `error:${error}` });
      setError("");
    }
  }, [error]);
  useEffect(() => {
    if (success) {
      toast.success(success, { id: `success:${success}` });
      setSuccess("");
    }
  }, [success]);
  function saveUniversityDirectory(entries:CustomUniversity[]) {
    try {
      const validated=parseCustomDirectory(entries);
      for (const item of validated) for (const alias of [item.name,...item.aliases]) {
        const known=universityIdentity(alias,universities);
        if(known&&known.id!==item.id)throw new Error(`“${alias}” already identifies ${known.official_english_name}. Use an alias belonging to the same institution.`);
      }
      const remaining=pendingUniversityReview.filter(item=>!validated.some(confirmed=>confirmed.id===item.id));
      setConfig(c=>({...c,custom_universities:validated}));
      setPendingUniversityReview(remaining);
      try {localStorage.setItem(CUSTOM_DIRECTORY_KEY,JSON.stringify({schema_version:2,universities:validated,pending_review:remaining}));}
      catch {setError("Classification retained for this cohort. Browser storage is unavailable; export the custom directory to retain it.");}
      invalidate();return true;
    } catch(e) {setError(message(e));return false;}
  }
  function confirmUniversity(entry:CustomUniversity) {return saveUniversityDirectory([...customUniversities.filter(item=>item.id!==entry.id),entry]);}
  async function importDirectory(file:File) {
    try { const imported=parseCustomDirectory(JSON.parse(await file.text())); const merged=new Map(customUniversities.map(item=>[item.id,item]));for(const entry of imported)merged.set(entry.id,entry);saveUniversityDirectory([...merged.values()]); }
    catch(e){setError(message(e));}
  }
  function exportDirectory() {
    const url=URL.createObjectURL(new Blob([JSON.stringify({schema_version:1,universities:customUniversities},null,2)],{type:"application/json"}));
    const link=document.createElement("a");link.href=url;link.download="AIP_Custom_University_Directory.json";link.click();URL.revokeObjectURL(url);
  }
  async function uploadSupport(file:File) {
    setLoading(true);
    try {const body=new FormData();body.append("file",file);const data=await jsonApi("/api/upload/support",{method:"POST",body});setSupport(data.support_members);setSupportDraft(String(data.support_members.length));invalidate();setSuccess("Support team imported. Review any missing gender or support category before continuing.");}
    catch(e){setError(message(e));}finally{setLoading(false);}
  }
  function invalidate() {
    setScheduleExtension(null);
    setAllocation(null);
    setGenerated(null);
    setMetrics(null);
  }
  function go(next: Step) {
    setStep(next);
    setError("");
    scrollTo({ top: 0, behavior: "smooth" });
  }
  async function uploadMaster(file: File) {
    setLoading(true);
    setError("");
    try {
      const body = new FormData();
      body.append("file", file);
      const data = await jsonApi("/api/upload", { method: "POST", body });
      if (
        participants.some((p) => p.name.trim()) &&
        !confirm(
          "Replace existing participants with this validated AIP Master file?",
        )
      )
        return;
      setParticipants(data.participants);
      setChemistry([]);
      setReview([]);
      invalidate();
      setSuccess(
        `${data.participants.length} new hires imported successfully.`,
      );
    } catch (e) {
      setError(message(e));
    } finally {
      setLoading(false);
    }
  }
  async function uploadChemistry(file: File) {
    if (!participants.length) {
      setError("Upload the AIP Master file first.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const body = new FormData();
      body.append("file", file);
      const parsed = await jsonApi("/api/upload/chemistry", {
        method: "POST",
        body,
      });
      const match = await jsonApi("/api/chemistry/match", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ participants, records: parsed.records }),
      });
      applyChemistry(match.matched);
      setChemistry(parsed.records);
      setReview(match.requires_review);
      setSuccess(
        `${match.matched.length} Chemistry records matched; ${match.requires_review.length} require review.`,
      );
    } catch (e) {
      setError(message(e));
    } finally {
      setLoading(false);
    }
  }
  function applyChemistry(records: ChemistryRecord[]) {
    setParticipants((list) =>
      list.map((p) => {
        const r = records.find((x) => x.participant_id === p.id);
        return r
          ? {
              ...p,
              attributes: {
                ...p.attributes,
                "Primary Chemistry": r.primary,
                "Secondary Chemistry": r.secondary,
              },
            }
          : p;
      }),
    );
    invalidate();
  }
  function resolve(record: ChemistryRecord, pid: string) {
    applyChemistry([{ ...record, participant_id: pid }]);
    setReview((list) =>
      list.filter((x) => x.source_name !== record.source_name),
    );
  }
  function editPerson(id: string, field: string, value: string) {
    setParticipants((list) =>
      list.map((p) =>
        p.id !== id
          ? p
          : field === "name"
            ? { ...p, name: value }
            : { ...p, attributes: { ...p.attributes, [field]: value, ...(field==="University"?{"University Category":null}:{}) } },
      ),
    );
    invalidate();
  }
  function resizePeople(count: number) {
    if (!Number.isInteger(count) || count < 1 || count > 60) {
      setError("Participant count must be between 1 and 60.");
      return;
    }
    if (
      count < participants.length &&
      participants.slice(count).some((p) => p.name.trim()) &&
      !confirm(
        `Remove ${participants.length - count} rows from the end? Populated participant information will be deleted.`,
      )
    )
      return;
    setParticipants((list) =>
      count > list.length
        ? [...list, ...Array.from({ length: count - list.length }, blankPerson)]
        : list.slice(0, count),
    );
    invalidate();
  }
  function createManualPeople() {
    const count = Number(manualDraft);
    if (!Number.isInteger(count) || count < 1 || count > 60) {
      setError("Choose a whole-number participant count between 1 and 60.");
      return;
    }
    setParticipants(Array.from({ length: count }, blankPerson));
    setShowManual(false);
    invalidate();
    setSuccess(
      `${count} blank participant rows created. Fill in each new hire's details below.`,
    );
  }
  function clearPeople() {
    if (
      !confirm(
        `Clear all participant details? All ${participants.length} rows will remain.`,
      )
    )
      return;
    setParticipants((list) =>
      list.map((p) => ({
        ...p,
        name: "",
        attributes: {
          ...p.attributes,
          Gender: "",
          University: "",
          "University Category": null,
          "L3 Offering": "",
          "Primary Chemistry": "",
          "Secondary Chemistry": "",
        },
      })),
    );
    setChemistry([]);
    setReview([]);
    invalidate();
  }
  function applySupport() {
    const n = Number(supportDraft);
    if (!Number.isInteger(n) || n < 0 || n > 30) {
      setError("Enter a support-team count from 0 to 30.");
      return;
    }
    if (
      n < support.length &&
      support.slice(n).some((x) => x.name.trim()) &&
      !confirm(`Remove ${support.length - n} populated support entries?`)
    ) {
      setSupportDraft(String(support.length));
      return;
    }
    setSupport((list) =>
      n > list.length
        ? [
            ...list,
            ...Array.from({ length: n - list.length }, () => ({
              id: uid("S"),
              name: "",
              gender: null,
              category: null,
            })),
          ]
        : list.slice(0, n),
    );
    invalidate();
  }
  function updateReflection(
    patch: Partial<Configuration["reflection_settings"]>,
  ) {
    setConfig((c) => ({
      ...c,
      reflection_settings: {
        ...(c.reflection_settings ?? initialConfig.reflection_settings),
        ...patch,
      },
    }));
    invalidate();
  }
  function validateData() {
    if (!participants.length) {
      setError("Upload the AIP Master file or add participants manually.");
      return false;
    }
    const incomplete = participants.filter(
      (p) =>
        !p.name.trim() ||
        !p.attributes.Gender ||
        !p.attributes.University ||
        !p.attributes["L3 Offering"],
    );
    if (incomplete.length) {
      setError(
        `${incomplete.length} new hires have missing name, gender, university, or L3 Offering information.`,
      );
      return false;
    }
    if (chemistryEnabled && !chemistry.length) {
      setError(
        "Upload the Business Chemistry Excel or turn off Business Chemistry allocation.",
      );
      return false;
    }
    if (chemistryEnabled && review.length) {
      setError(
        `${review.length} Business Chemistry matches still require review.`,
      );
      return false;
    }
    if (
      chemistryEnabled &&
      participants.some(
        (p) =>
          !p.attributes["Primary Chemistry"] ||
          !p.attributes["Secondary Chemistry"],
      )
    ) {
      setError(
        "Every new hire must have resolved Primary and Secondary Business Chemistry values.",
      );
      return false;
    }
    return true;
  }
  function validateTeam() {
    if (
      faculty.some(
        (x) =>
          !x.name.trim() ||
          !OFFERINGS.includes(x.offering as (typeof OFFERINGS)[number]),
      )
    ) {
      setError(
        "Enter each faculty name and select one of the five valid L3 Offerings.",
      );
      return false;
    }
    if (support.some((x) => !x.name.trim() || !x.gender || !x.category)) {
      setError("Complete every support team member’s name, gender, and support category.");
      return false;
    }
    if(support.filter(member=>member.category==="Support Lead").length<2){
      setError("At least two Support Leads are required so that each BUS Team has an experienced support member.");return false;
    }
    return true;
  }
  async function generate() {
    if (!validateData() || !validateTeam()) return;
    if(unresolvedUniversities.length){go("data");setError("University classification required. Confirm every university category before generating allocations.");return;}
    if (
      allocation &&
      !confirm("Regenerating will overwrite current manual edits. Continue?")
    )
      return;
    setLoading(true);
    setError("");
    try {
      const data = await jsonApi("/api/optimize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          participants: normalizedParticipants,
          faculty_members: faculty,
          support_members: support,
          configuration: config,
        }),
      });
      setAllocation(data.allocation);
      setGenerated(structuredClone(data.allocation));
      setMetrics(data.metrics);
      setTab("main");
      setScheduleExtension(null);
      go("results");
    } catch (e) {
      const detail=message(e),suggested=detail.match(/extend the final end time to (\d{1,2}:\d{2})/i)?.[1];
      if(suggested)setScheduleExtension(suggested.padStart(5,"0"));
      setError(detail);
    } finally {
      setLoading(false);
    }
  }
  async function applyDraftEdit(
    participantId: string,
    targetGroupId: string,
    swapWithId?: string,
    allowOverride = false,
  ) {
    if (!editDraft) return;
    try {
      const before = structuredClone(editDraft);
      const data = await jsonApi("/api/allocations/edit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          participants: normalizedParticipants,
          faculty_members: faculty,
          support_members: support,
          configuration: config,
          allocation: editDraft,
          activity_id: tab,
          participant_id: participantId,
          target_group_id: targetGroupId,
          swap_with_id: swapWithId || null,
          allow_override: allowOverride,
        }),
      });
      if (data.requires_confirmation) {
        setPendingEdit({
          participantId,
          targetGroupId,
          swapWithId,
          conflicts: data.conflicts,
        });
        return;
      }
      setUndoStack((stack) => [...stack, before]);
      setEditDraft(data.allocation);
      const affected = new Set([participantId, swapWithId].filter(Boolean));
      setDraftOverrides((items) => [
        ...items.map((item) =>
          item.active && item.participantIds.some((id) => affected.has(id))
            ? { ...item, active: false }
            : item,
        ),
        ...(data.conflicts || []).map((item: EditConflict) => ({
          id: uid("override"),
          activity: tab,
          participantIds: item.participant_ids,
          rule: item.rule,
          message: item.message,
          timestamp: new Date().toISOString(),
          active: true,
          policySensitive: item.policy_sensitive,
        })),
      ]);
      setPendingEdit(null);
      setSwapA("");
      setSwapB("");
      const first = pmap[participantId]?.name || participantId,
        second = swapWithId ? pmap[swapWithId]?.name || swapWithId : "";
      setSuccess(
        allowOverride
          ? "Administrator override applied to the draft."
          : tab === "reflection" && swapWithId
            ? `${first} and ${second}'s reflection times were swapped.`
            : swapWithId
              ? "Draft swap applied."
              : "Draft move applied.",
      );
    } catch (e) {
      setError(message(e));
    }
  }
  async function swap() {
    if (!editDraft || !swapA || !swapB || swapA === swapB) return;
    const target = current?.groups.find((group) =>
      group.participant_ids.includes(swapB),
    );
    if (target) await applyDraftEdit(swapA, target.id, swapB);
  }
  async function saveDraft() {
    if (!editDraft) return;
    try {
      const payload = {
        participants: normalizedParticipants,
        faculty_members: faculty,
        support_members: support,
        configuration: config,
        allocation: editDraft,
      };
      const result = await jsonApi("/api/allocations/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!result.valid) {
        setError(result.errors.join("; "));
        return;
      }
      const updatedMetrics = await jsonApi("/api/allocations/score", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setAllocation(structuredClone(editDraft));
      setOverrides(draftOverrides);
      setMetrics(updatedMetrics);
      setEditDraft(null);
      setUndoStack([]);
      setEditMode(false);
      setSuccess("Changes saved. Exports now use the updated assignments.");
    } catch (e) {
      setError(message(e));
    }
  }
  function cancelDraft() {
    setEditDraft(null);
    setDraftOverrides(overrides);
    setUndoStack([]);
    setEditMode(false);
    setSwapA("");
    setSwapB("");
  }
  function undoDraft() {
    const previous = undoStack.at(-1);
    if (!previous) return;
    setEditDraft(structuredClone(previous));
    setUndoStack((stack) => stack.slice(0, -1));
    setSuccess("Last draft change undone.");
  }
  function dragEnd(event: DragEndEvent) {
    const active = String(event.active.id),
      over = event.over ? String(event.over.id) : "";
    if (!editDraft || !active.startsWith("drag:") || !over) return;
    const participantId = active.split(":").slice(2).join(":"),
      parts = over.split(":"),
      kind = parts[0],
      targetGroupId = parts[1],
      swapWithId = kind === "person" ? parts.slice(2).join(":") : undefined;
    const activity = editDraft.activities.find(
        (item) => item.activity_id === tab,
      ),
      source = activity?.groups.find((group) =>
        group.participant_ids.includes(participantId),
      ),
      target = activity?.groups.find((group) => group.id === targetGroupId);
    if (!source || !target || (source.id === target.id && !swapWithId)) return;
    if (
      !swapWithId &&
      (tab==="hotel"?target.participant_ids.length>=2&&!config.allow_accommodation_policy_overrides:target.participant_ids.length>=source.participant_ids.length)
    ) {
      setError(
        "That group is already at capacity. Drop onto a participant in the destination group to swap instead.",
      );
      return;
    }
    applyDraftEdit(participantId, targetGroupId, swapWithId);
  }
  const exportBody = allocation
    ? {
        participants: normalizedParticipants,
        faculty_members: faculty,
        support_members: support,
        configuration: config,
        allocation,
      }
    : null;
  function requestExport(action: () => Promise<void>) {
    const sensitive = overrides.filter(
      (item) => item.active && item.policySensitive,
    );
    const run = () =>
      action()
        .then(() => setSuccess("Export downloaded successfully."))
        .catch((e) => setError(message(e)));
    if (sensitive.length) {
      setPendingExport(() => run);
    } else run();
  }
  return (
    <div className={`min-h-screen bg-mist ${step==="results"?"results-workspace":""}`}>
      <Header count={participants.length} />
      <main className="mx-auto max-w-7xl px-5 py-8">
        <Progress step={step} go={go} />
        {step === "data" && (
          <section>
            <Title
              title="Upload Week 2 data"
              text="Upload the AIP Master workbook and optionally include Business Chemistry in allocation."
            />
            <label className="card mb-5 flex cursor-pointer items-center gap-3 p-4">
              <input
                className="h-5 w-5 accent-sky"
                type="checkbox"
                checked={chemistryEnabled}
                onChange={(e) => {
                  const enabled = e.target.checked === true;
                  setConfig((c) => ({
                    ...c,
                    include_business_chemistry: enabled,
                  }));
                  invalidate();
                  setError("");
                  setSuccess(
                    `Business Chemistry allocation ${enabled ? "enabled" : "disabled"}. Regenerate groups before exporting.`,
                  );
                }}
              />
              <span>
                <b>Include Business Chemistry in group allocation</b>
                <span className="block text-sm text-slate-500">
                  When enabled, the Business Chemistry workbook and resolved
                  matches are required.
                </span>
              </span>
            </label>
            <div className="grid gap-5 md:grid-cols-2">
              <UploadCard
                title="AIP Master Excel"
                text="Candidate details, university, gender, offering, and original master fields."
                ready={participants.length > 0}
                action={() => masterInput.current?.click()}
              />
              <UploadCard
                title={`Business Chemistry Excel${chemistryEnabled ? "" : " (Disabled)"}`}
                text={
                  chemistryEnabled
                    ? "Name, Primary, and Secondary Chemistry."
                    : "Not required and not used in allocation."
                }
                ready={chemistry.length > 0}
                disabled={!chemistryEnabled}
                action={() => chemInput.current?.click()}
              />
            </div>
            <input
              ref={masterInput}
              hidden
              type="file"
              accept=".xlsx"
              onChange={(e) => {
                const f = e.currentTarget.files?.[0];
                e.currentTarget.value = "";
                if (f) uploadMaster(f);
              }}
            />
            <input
              ref={chemInput}
              hidden
              type="file"
              accept=".xlsx"
              onChange={(e) => {
                const f = e.currentTarget.files?.[0];
                e.currentTarget.value = "";
                if (f) uploadChemistry(f);
              }}
            />
            {participants.length === 0 && !showManual && (
              <button
                className="btn btn-outline mt-5"
                onClick={() => {
                  setShowManual(true);
                  setError("");
                }}
              >
                <Plus size={17} />
                Fill Data Manually
              </button>
            )}
            {participants.length === 0 && showManual && (
              <ManualParticipantCount
                value={manualDraft}
                change={setManualDraft}
                create={createManualPeople}
                cancel={() => setShowManual(false)}
              />
            )}{" "}
            {chemistryEnabled && review.length > 0 && (
              <Review
                records={review}
                people={participants}
                resolve={resolve}
              />
            )}{" "}
            {participants.length > 0 && (
              <ParticipantTable
                people={participants}
                edit={editPerson}
                add={() => {
                  setParticipants((x) => [...x, blankPerson()]);
                  invalidate();
                }}
                remove={(id) => {
                  setParticipants((x) => x.filter((p) => p.id !== id));
                  invalidate();
                }}
                resize={resizePeople}
                clear={clearPeople}
                universities={allUniversities}
              />
            )}
            {pendingUniversityReview.length>0&&<p role="status" className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">{pendingUniversityReview.length} saved university grouping {pendingUniversityReview.length===1?"mapping needs":"mappings need"} Public or Private confirmation. Earlier categories have been removed. Review these institutions when they appear in this cohort: {pendingUniversityReview.map(item=>item.name).join(", ")}.</p>}
            {participants.length>0&&<>
              <UniversityReview people={participants} directory={allUniversities} custom={customUniversities} pending={pendingUniversityReview} confirm={confirmUniversity}/>
              <div className="mt-3 flex flex-wrap gap-2">
                <button className="btn btn-outline" onClick={()=>directoryInput.current?.click()}>Import custom university directory</button>
                <button className="btn btn-outline" onClick={exportDirectory}>Export custom university directory</button>
                <input hidden ref={directoryInput} type="file" accept=".json,application/json" onChange={e=>{const file=e.currentTarget.files?.[0];e.currentTarget.value="";if(file)importDirectory(file)}}/>
              </div>
            </>}
            <Next
              onClick={() => validateData() && go("team")}
              label="Continue to Faculty & Support"
            />
          </section>
        )}
        {step === "team" && (
          <section>
            <TopBack onClick={() => go("data")} step="Step 2 of 4" />
            <Title
              title="Faculty & support team"
              text="Faculty attend My Reflections. Support Leads and Analyst Support join BUS Teams. Everyone receives a hotel room assignment."
            />
            <div className="grid gap-5 lg:grid-cols-2">
              <div className="card overflow-visible p-6">
                <h2 className="text-xl font-extrabold">
                  Exactly three faculty members
                </h2>
                {faculty.map((f, i) => (
                  <div className="mt-4 grid gap-3 sm:grid-cols-2" key={f.id}>
                    <input
                      className="input"
                      placeholder={`Faculty ${i + 1} name`}
                      value={f.name ?? ""}
                      onChange={(e) =>
                        setFaculty((x) =>
                          x.map((y) =>
                            y.id === f.id ? { ...y, name: e.target.value } : y,
                          ),
                        )
                      }
                    />
                    <OfferingCombobox
                      label={`Faculty ${i + 1} offering`}
                      value={f.offering ?? ""}
                      change={(offering) =>
                        setFaculty((x) =>
                          x.map((y) =>
                            y.id === f.id ? { ...y, offering } : y,
                          ),
                        )
                      }
                    />
                  </div>
                ))}

              </div>
              <div className="card p-6">
                <h2 className="text-xl font-extrabold">Support team members</h2>
                <div className="mt-4 flex gap-3">
                  <input
                    className="input w-28"
                    type="number"
                    aria-label="Support team count"
                    min="0"
                    max="30"
                    value={supportDraft ?? ""}
                    onChange={(e) => setSupportDraft(e.target.value)}
                  />
                  <button className="btn btn-outline" onClick={applySupport}>
                    Apply Count
                  </button>
                </div>
                <p className="mt-3 text-sm text-slate-500">Support Leads coordinate the buses; Analyst Support assist the onboarding team. At least two Support Leads are required.</p>
                <button className="btn btn-outline mt-3" onClick={()=>supportInput.current?.click()}>Import support Excel</button>
                <input ref={supportInput} hidden type="file" accept=".xlsx" onChange={e=>{const file=e.currentTarget.files?.[0];e.currentTarget.value="";if(file)uploadSupport(file)}}/>
                {support.map((s, i) => (
                  <div className="mt-4 grid gap-2 border-t pt-3 sm:grid-cols-2" key={s.id}>
                    <input className="input sm:col-span-2" aria-label={`Support member ${i+1} name`} placeholder={`Support member ${i+1} name`} value={s.name??""} onChange={e=>{setSupport(list=>list.map(member=>member.id===s.id?{...member,name:e.target.value}:member));invalidate();}}/>
                    <select className="input" aria-label={`Support member ${i+1} gender`} value={s.gender??""} onChange={e=>{setSupport(list=>list.map(member=>member.id===s.id?{...member,gender:e.target.value as SupportMember["gender"]}:member));invalidate();}}><option value="">Choose gender</option><option>Male</option><option>Female</option></select>
                    <select className="input" aria-label={`Support member ${i+1} category`} value={s.category??""} onChange={e=>{setSupport(list=>list.map(member=>member.id===s.id?{...member,category:e.target.value as SupportMember["category"]}:member));invalidate();}}><option value="">Choose support category</option><option value="Support Lead">Support Lead</option><option value="Analyst Support">Analyst Support</option></select>
                  </div>
                ))}
                <p className="mt-3 text-xs text-slate-500">Support Leads: {support.filter(s=>s.category==="Support Lead").length} · Analyst Support: {support.filter(s=>s.category==="Analyst Support").length}</p>
              </div>
            </div>
            <ReflectionSettingsPanel
              settings={reflectionSettings}
              participants={participants}
              facultyCount={faculty.length}
              change={updateReflection}
            />
            <Next
              onClick={() => validateTeam() && go("sizes")}
              label="Continue to Group Sizes"
            />
          </section>
        )}
        {step === "sizes" && (
          <section>
            <TopBack onClick={() => go("team")} step="Step 3 of 4" />
            <Title
              title="Configure group sizes"
              text="All six allocations will be generated together."
            />
            <div className="grid gap-5 lg:grid-cols-3">
              {config.activities.map((a) => (
                <SizeCard
                  key={a.id}
                  activity={a}
                  count={
                    participants.length
                      ? Math.ceil(participants.length / a.value)
                      : 0
                  }
                  change={(v) =>
                    setConfig((c) => ({
                      ...c,
                      activities: c.activities.map((x) =>
                        x.id === a.id ? { ...x, value: v } : x,
                      ),
                    }))
                  }
                />
              ))}
            </div>
            <div className="mt-5 grid gap-3 sm:grid-cols-3">
              {[
                ["BUS Teams", "Fixed at 2"],
                ["My Reflections", "3 faculty lists"],
                ["Hotel Rooms", "Maximum 2 occupants"],
              ].map((x) => (
                <div className="card p-5" key={x[0]}>
                  <b>{x[0]}</b>
                  <p className="text-sm text-slate-500">{x[1]}</p>
                </div>
              ))}
            </div>
            {scheduleExtension&&<div role="status" className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">My Reflections needs a longer schedule to respect the protected break. Earliest feasible completion: <b>{scheduleExtension}</b>.<button className="btn btn-outline ml-3" onClick={()=>{const end=scheduleExtension;updateReflection({end_time:end});setSuccess(`Final end time set to ${end}. Generate allocations to apply the extended schedule.`);}}>Set final end time to {scheduleExtension}</button></div>}
            {unresolvedUniversities.length>0&&<div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">University classification required before generation. <button className="font-bold underline" onClick={()=>go("data")}>Review classifications</button></div>}
            <Next
              onClick={generate}
              label={
                loading
                  ? "Generating all six allocations…"
                  : "Generate Week 2 Allocations"
              }
              disabled={loading}
            />
          </section>
        )}
        {step === "results" && (
          <section className="results-root">
            <TopBack onClick={() => go("sizes")} step="Step 4 of 4" />
            <div className="results-page-header"><div><p className="result-eyebrow">AIP onboarding · Results</p><h1>Week 2 allocations</h1><p className="results-page-description">Review your groups, schedules, and accommodation.</p></div>{allocation&&<ResultsLegend/>}</div>
            {allocation && (
              <>
                <div className="results-controls">
                  <nav className="results-tabs" aria-label="Allocation activities">
                    {displayedAllocation?.activities.map((a) => {
                      const Icon=resultActivityIcons[a.activity_id]??Users;
                      return (
                      <button
                        className={`results-tab ${tab === a.activity_id ? "is-active" : ""}`}
                        aria-pressed={tab===a.activity_id}
                        key={a.activity_id}
                        onClick={() => {
                          setTab(a.activity_id);
                          setSwapA("");
                          setSwapB("");
                        }}
                      >
                        <Icon size={16} aria-hidden="true"/>
                        {a.activity_name}
                      </button>
                    );})}
                  </nav>
                  {!editMode ? (
                    <div className="results-actions">
                      <div>
                        <p className="result-control-label">
                          Manage allocations
                        </p>
                        <button
                          className="btn btn-outline mt-2"
                          onClick={() => {
                            setEditDraft(structuredClone(allocation));
                            setDraftOverrides(structuredClone(overrides));
                            setUndoStack([]);
                            setEditMode(true);
                          }}
                        >
                          <PencilLine size={15} aria-hidden="true"/>
                          Edit Teams
                        </button>
                      </div>
                      <div>
                        <p className="result-control-label lg:text-right">
                          Export saved results
                        </p>
                        <div className="mt-2 flex flex-wrap gap-2 lg:justify-end">
                          {overrides.some((x) => x.active) && (
                            <button
                              className="btn border border-amber-300 bg-amber-50 text-amber-900"
                              onClick={() => setShowOverrides(true)}
                            >
                              {overrides.filter((x) => x.active).length} manual
                              overrides
                            </button>
                          )}
                          <button
                            className="btn btn-outline"
                            onClick={() =>
                              exportBody &&
                              requestExport(() =>
                                download(
                                  "/api/export/editable",
                                  exportBody,
                                  "AIP_Week2_Allocations.xlsx",
                                ),
                              )
                            }
                          >
                            <Download size={16} />
                            Editable Excel
                          </button>
                          <button
                            className="btn btn-primary"
                            onClick={() =>
                              exportBody &&
                              requestExport(() =>
                                download(
                                  "/api/export/pdf",
                                  exportBody,
                                  "AIP_Week2_Final.pdf",
                                ),
                              )
                            }
                          >
                            <Download size={16} />
                            Final PDF
                          </button>
                          <IndividualPdfMenu
                            open={individualOpen}
                            toggle={() => setIndividualOpen((value) => !value)}
                            close={() => setIndividualOpen(false)}
                            activities={allocation.activities}
                            body={exportBody}
                          />
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="results-edit-toolbar">
                      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="edit-status-dot" aria-hidden="true"/>
                            <h2 className="font-semibold text-navy">
                              Team editing mode
                            </h2>
                          </div>
                          <p className="mt-1 text-sm text-slate-600">
                            Drag to exchange assignments or use Switch Participants. Your changes stay in this draft until saved.
                          </p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <button
                            className="btn btn-primary"
                            onClick={saveDraft}
                          >
                            <Check size={15} aria-hidden="true"/>
                            Save Changes
                          </button>
                          <button
                            className="btn btn-outline"
                            onClick={cancelDraft}
                          >
                            Cancel Changes
                          </button>
                          <button
                            className="btn btn-outline"
                            disabled={!undoStack.length}
                            title={undoStack.length?"Undo the last draft edit":"Make a change to enable Undo"}
                            onClick={undoDraft}
                          >
                            <Undo2 size={15} aria-hidden="true"/>
                            Undo Last Change
                          </button>
                          <button
                            className="btn border border-red-200 bg-white text-red-700 hover:bg-red-50"
                            onClick={() => {
                              if (!generated) return;
                              setUndoStack((stack) =>
                                editDraft
                                  ? [...stack, structuredClone(editDraft)]
                                  : stack,
                              );
                              setEditDraft(structuredClone(generated));
                              setDraftOverrides([]);
                            }}
                          >
                            <RotateCcw size={15} aria-hidden="true"/>
                            Reset to Generated
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
                {editMode && (
                  <label className="results-policy-note">
                    <input
                      type="checkbox"
                      checked={
                        config.allow_accommodation_policy_overrides === true
                      }
                      onChange={(e) =>
                        setConfig((c) => ({
                          ...c,
                          allow_accommodation_policy_overrides:
                            e.target.checked,
                        }))
                      }
                    />
                    <span>
                      <b>Allow accommodation-policy override confirmations</b>
                      <span className="block text-amber-800">
                        Leave off when mixed-gender rooms or over-capacity rooms
                        are prohibited by policy.
                      </span>
                    </span>
                  </label>
                )}
                {current&&<ResultSectionHeader title={current.activity_name} activityId={current.activity_id} groups={current.groups.length}/>}
                {editMode ? (
                  <DndContext sensors={sensors} onDragEnd={dragEnd}>
                    {current && (
                      <>
                        <EditPanel
                          activity={current}
                          people={pmap}
                          support={smap}
                          faculty={faculty}
                          chemistryEnabled={chemistryEnabled}
                          a={swapA}
                          b={swapB}
                          setA={setSwapA}
                          setB={setSwapB}
                          swap={swap}
                        />
                        <AllocationCards
                          activity={current}
                          people={pmap}
                          support={smap}
                          faculty={faculty}
                          chemistryEnabled={chemistryEnabled}
                          reflectionSettings={reflectionSettings}
                          selectedIds={[swapA,swapB]}
                          editable
                        />
                      </>
                    )}
                  </DndContext>
                ) : (
                  <AllocationCards
                    activity={current}
                    people={pmap}
                    support={smap}
                    faculty={faculty}
                    chemistryEnabled={chemistryEnabled}
                    reflectionSettings={reflectionSettings}
                  />
                )}
                {!current&&<div className="results-empty"><Users size={28} aria-hidden="true"/><h2>No allocations to display</h2><p>Choose an activity to review its saved assignments.</p></div>}
              </>
            )}
          </section>
        )}
        {pendingEdit && (
          <ConfirmationDialog
            title={
              pendingEdit.conflicts.some((x) => x.policy_sensitive)
                ? "Accommodation policy conflict"
                : "Manual edit conflict detected"
            }
            conflicts={pendingEdit.conflicts}
            cancel={() => setPendingEdit(null)}
            confirm={
              pendingEdit.conflicts.every((x) => x.overridable)
                ? () =>
                    applyDraftEdit(
                      pendingEdit.participantId,
                      pendingEdit.targetGroupId,
                      pendingEdit.swapWithId,
                      true,
                    )
                : undefined
            }
          />
        )}
        {showOverrides && (
          <OverrideDialog
            overrides={overrides.filter((x) => x.active)}
            close={() => setShowOverrides(false)}
          />
        )}
        {pendingExport && (
          <ConfirmationDialog
            title="Policy-sensitive overrides included"
            conflicts={overrides
              .filter((x) => x.active && x.policySensitive)
              .map((x) => ({
                rule: x.rule,
                message: x.message,
                policy_sensitive: true,
                overridable: true,
                participant_ids: x.participantIds,
              }))}
            cancel={() => setPendingExport(null)}
            confirm={() => {
              const action = pendingExport;
              setPendingExport(null);
              action();
            }}
            confirmLabel="Export Current Assignments"
          />
        )}
      </main>
    </div>
  );
}

function Header({ count }: { count: number }) {
  return (
    <header className="border-b bg-white">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-5">
        <div className="flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-xl bg-gradient-to-br from-sky to-teal text-white">
            <Sparkles />
          </div>
          <b className="text-navy">AIP WEEK 2 GROUP ALLOCATOR</b>
        </div>
        {count > 0 && (
          <span className="rounded-full bg-blue-50 px-4 py-2 text-sm text-blue-800">
            {count} new hires
          </span>
        )}
      </div>
    </header>
  );
}
function Progress({ step, go }: { step: Step; go: (s: Step) => void }) {
  const active = steps.findIndex((x) => x.id === step);
  return (
    <nav className="card mb-8 overflow-x-auto p-4">
      <ol className="flex min-w-[650px]">
        {steps.map((s, i) => (
          <li className="flex flex-1 items-center" key={s.id}>
            <button
              className="flex items-center gap-2"
              onClick={() => i <= active && go(s.id)}
            >
              <span
                className={`grid h-9 w-9 place-items-center rounded-full text-sm font-bold ${i === active ? "bg-navy text-white" : i < active ? "bg-teal text-white" : "bg-slate-100"}`}
              >
                {i < active ? <Check size={16} /> : i + 1}
              </span>
              <b className="text-sm">{s.label}</b>
            </button>
            {i < 3 && <div className="mx-3 h-px flex-1 bg-slate-200" />}
          </li>
        ))}
      </ol>
    </nav>
  );
}
function Title({ title, text }: { title: string; text: string }) {
  const hidden =
    text ===
      "Upload the AIP Master workbook and optionally include Business Chemistry in allocation." ||
    text ===
      "Faculty participate only in My Reflections. Support members participate only in BUS Teams." ||
    text === "All six allocations will be generated together.";
  return (
    <div className="mb-7">
      <h1 className="text-4xl font-extrabold text-navy">{title}</h1>
      {!hidden && <p className="mt-2 text-slate-500">{text}</p>}
    </div>
  );
}
function ConfirmationDialog({
  title,
  conflicts,
  cancel,
  confirm,
  confirmLabel = "Override & Save",
}: {
  title: string;
  conflicts: EditConflict[];
  cancel: () => void;
  confirm?: () => void;
  confirmLabel?: string;
}) {
  const sensitive = conflicts.some((x) => x.policy_sensitive);
  return (
    <div
      className="fixed inset-0 z-[100] grid place-items-center bg-navy/55 p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) cancel();
      }}
    >
      <div
        className={`w-full max-w-xl rounded-2xl border bg-white p-6 shadow-2xl ${sensitive ? "border-red-400 ring-4 ring-red-100" : "border-slate-200"}`}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirmation-title"
      >
        <h2
          id="confirmation-title"
          className={`text-xl font-extrabold ${sensitive ? "text-red-800" : "text-navy"}`}
        >
          {title}
        </h2>
        {sensitive && (
          <p className="mt-2 rounded-lg bg-red-50 p-3 text-sm font-semibold text-red-800">
            This exception may require accommodation-policy approval and is not
            automatically policy-compliant.
          </p>
        )}
        <ul className="mt-4 space-y-2">
          {conflicts.map((item, index) => (
            <li
              className="rounded-lg bg-slate-50 p-3 text-sm text-slate-700"
              key={`${item.rule}-${index}`}
            >
              {item.message}
              {!item.overridable && (
                <b className="mt-1 block text-red-700">
                  This restriction is currently non-overridable. Change the
                  policy setting or choose another assignment.
                </b>
              )}
            </li>
          ))}
        </ul>
        <div className="mt-6 flex justify-end gap-3">
          <button autoFocus className="btn btn-outline" onClick={cancel}>
            Cancel
          </button>
          {confirm && (
            <button
              className={`btn ${sensitive ? "bg-red-700 text-white" : "btn-primary"}`}
              onClick={confirm}
            >
              {confirmLabel}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
function OverrideDialog({
  overrides,
  close,
}: {
  overrides: ManualOverride[];
  close: () => void;
}) {
  return (
    <div className="fixed inset-0 z-[100] grid place-items-center bg-navy/55 p-4">
      <div
        className="w-full max-w-xl rounded-2xl bg-white p-6 shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="override-title"
      >
        <h2 id="override-title" className="text-xl font-extrabold text-navy">
          Active manual overrides
        </h2>
        <div className="mt-4 max-h-80 space-y-3 overflow-y-auto">
          {overrides.map((item) => (
            <article className="rounded-xl border p-3" key={item.id}>
              <div className="flex justify-between gap-3">
                <b className="capitalize">
                  {item.activity} · {item.rule.replaceAll("_", " ")}
                </b>
                <time className="text-xs text-slate-400">
                  {new Date(item.timestamp).toLocaleString()}
                </time>
              </div>
              <p className="mt-1 text-sm text-slate-600">{item.message}</p>
            </article>
          ))}
        </div>
        <div className="mt-5 flex justify-end">
          <button autoFocus className="btn btn-primary" onClick={close}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
function UploadCard({
  title,
  ready,
  action,
  disabled = false,
}: {
  title: string;
  text: string;
  ready: boolean;
  action: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      disabled={disabled}
      className={`card flex items-center gap-4 p-6 text-left hover:border-sky disabled:cursor-not-allowed disabled:opacity-55 ${ready ? "border-teal ring-4 ring-emerald-50" : ""}`}
      onClick={action}
    >
      <div className="grid h-12 w-12 place-items-center rounded-xl bg-blue-50 text-sky">
        {ready ? <Check /> : <UploadCloud />}
      </div>
      <h2 className="font-extrabold">{title}</h2>
    </button>
  );
}
function IndividualPdfMenu({
  open,
  toggle,
  close,
  activities,
  body,
}: {
  open: boolean;
  toggle: () => void;
  close: () => void;
  activities: Allocation["activities"];
  body: unknown;
}) {
  const labels: Record<string, { label: string; file: string }> = {
    main: { label: "Main Groups", file: "AIP_Main_Groups.pdf" },
    team: { label: "Team Building", file: "AIP_Team_Building.pdf" },
    quiz: { label: "Quiz Night", file: "AIP_Quiz_Night.pdf" },
    sports: { label: "Sports Day", file: "AIP_Sports_Day.pdf" },
    bus: { label: "Bus Allocation", file: "AIP_Bus_Allocation.pdf" },
    reflection: { label: "My Reflections", file: "AIP_My_Reflections.pdf" },
    hotel: { label: "Hotel Rooms", file: "AIP_Hotel_Rooms.pdf" },
  };
  const options = activities.filter((activity) => labels[activity.activity_id]);
  return (
    <div className="relative">
      <button className="btn btn-outline" aria-expanded={open} onClick={toggle}>
        <Download size={16} />
        Individual PDF
        <ChevronDown size={15} />
      </button>
      {open && (
        <div className="absolute right-0 z-50 mt-2 min-w-56 rounded-xl border bg-white p-1.5 shadow-xl">
          {options.map((activity) => {
            const option = labels[activity.activity_id];
            return (
              <button
                className="block w-full rounded-lg px-3 py-2 text-left text-sm font-semibold text-navy hover:bg-blue-50"
                key={activity.activity_id}
                onClick={() => {
                  close();
                  download(
                    `/api/export/pdf/${encodeURIComponent(activity.activity_id)}`,
                    body,
                    option.file,
                  );
                }}
              >
                {option.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
function OfferingCombobox({
  label,
  value,
  change,
}: {
  label: string;
  value: string;
  change: (value: string) => void;
}) {
  const [open, setOpen] = useState(false),
    [query, setQuery] = useState(value),
    [active, setActive] = useState(0);
  useEffect(() => setQuery(value), [value]);
  const search =
      open && query === value ? "" : query.trim().toLocaleLowerCase(),
    options = OFFERINGS.filter((option) =>
      option.toLocaleLowerCase().includes(search),
    );
  function choose(option: string) {
    change(option);
    setQuery(option);
    setOpen(false);
    setActive(0);
  }
  return (
    <div className="relative">
      <input
        aria-label={label}
        aria-autocomplete="list"
        aria-expanded={open}
        role="combobox"
        className="input pr-9"
        placeholder="Select faculty offering..."
        value={open ? query : value}
        onFocus={() => {
          setOpen(true);
          setActive(0);
        }}
        onBlur={() =>
          setTimeout(() => {
            setOpen(false);
            setQuery(value);
          }, 120)
        }
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          setActive(0);
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((index) => Math.min(index + 1, options.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((index) => Math.max(index - 1, 0));
          } else if (e.key === "Enter" && options.length) {
            e.preventDefault();
            choose(options[active]);
          } else if (e.key === "Escape") {
            setOpen(false);
            setQuery(value);
          }
        }}
      />
      <ChevronDown
        className="pointer-events-none absolute right-3 top-3 text-slate-400"
        size={16}
      />
      {open && (
        <div
          role="listbox"
          className="absolute z-40 mt-1 w-full rounded-xl border bg-white p-1 shadow-xl"
        >
          {options.length ? (
            options.map((option, index) => (
              <button
                type="button"
                role="option"
                aria-selected={option === value}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => choose(option)}
                className={`block w-full rounded-lg px-3 py-2 text-left text-sm font-semibold ${index === active ? "bg-blue-50 text-navy" : "hover:bg-slate-50"}`}
                key={option}
              >
                {option}
              </button>
            ))
          ) : (
            <p className="px-3 py-2 text-sm text-slate-500">
              No matching offering
            </p>
          )}
        </div>
      )}
    </div>
  );
}
function ManualParticipantCount({
  value,
  change,
  create,
  cancel,
}: {
  value: string;
  change: (value: string) => void;
  create: () => void;
  cancel: () => void;
}) {
  return (
    <div className="card mt-5 max-w-xl p-6">
      <h2 className="text-xl font-extrabold text-navy">
        Fill participant data manually
      </h2>
      <p className="mt-1 text-sm text-slate-500">
        Choose how many participant rows you need. You can adjust the count
        later.
      </p>
      <label
        className="mt-5 block text-sm font-bold"
        htmlFor="manual-participant-count"
      >
        Number of participants
      </label>
      <div className="mt-2 flex flex-wrap gap-3">
        <input
          autoFocus
          id="manual-participant-count"
          className="input w-40"
          type="number"
          min="1"
          max="60"
          step="1"
          value={value ?? ""}
          onChange={(e) => change(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") create();
          }}
        />
        <button className="btn btn-primary" onClick={create}>
          Create Participant Rows
          <ArrowRight size={17} />
        </button>
        <button className="btn btn-outline" onClick={cancel}>
          Cancel
        </button>
      </div>
      <p className="mt-2 text-xs text-slate-500">
        Choose between 1 and 60 participants.
      </p>
    </div>
  );
}
function ReflectionSettingsPanel({
  settings,
  participants,
  facultyCount,
  change,
}: {
  settings: Configuration["reflection_settings"];
  participants: Participant[];
  facultyCount: number;
  change: (patch: Partial<Configuration["reflection_settings"]>) => void;
}) {
  const eligible=eligiblePrayerParticipants(participants);
  const selected = new Set(prunePrayerSelection(settings.selected_participant_ids,participants));
  const toMinutes = (value: string) => {
    const [h, m] = value.split(":").map(Number);
    return Number.isFinite(h) && Number.isFinite(m) ? h * 60 + m : 0;
  };
  const available = Math.max(
      0,
      Math.floor(
        (toMinutes(settings.prayer_deadline) - toMinutes(settings.start_time)) /
          Math.max(1, settings.session_duration_minutes),
      ),
    ),
    capacity = available * facultyCount;
  return (
    <div className="card mt-5 p-6">
      <label className="flex cursor-pointer items-center gap-3">
        <input
          className="h-5 w-5 accent-sky"
          type="checkbox"
          checked={settings.enabled === true}
          onChange={(e) => change({ enabled: e.target.checked === true })}
        />
        <span>
          <b className="text-lg text-navy">Enable My Reflections Time Optimization (For Friday Prayer)</b>
          <span className="block text-sm text-slate-500">
            Schedule appointments before prayer and continue after the protected break.
          </span>
        </span>
      </label>
      {settings.enabled && (
        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <div>
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-extrabold">Friday prayer accommodation</h3>
                <p className="text-sm text-slate-500">
                  Explicitly select male participants who need the prayer break protected. Unselected participants can continue during the break.
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  className="text-sm font-bold text-sky"
                  onClick={() =>
                    change({ selected_participant_ids: eligible.map((p) => p.id) })
                  }
                >
                  Select All
                </button>
                <button
                  className="text-sm font-bold text-slate-500"
                  onClick={() => change({ selected_participant_ids: [] })}
                >
                  Deselect All
                </button>
              </div>
            </div>
            <div className="mt-3 max-h-64 space-y-2 overflow-y-auto rounded-xl border p-3">
              {eligible.length ? (
                eligible.map((p) => (
                  <label
                    className="flex cursor-pointer items-center gap-3 rounded-lg p-2 hover:bg-slate-50"
                    key={p.id}
                  >
                    <input
                      type="checkbox"
                      checked={selected.has(p.id)}
                      onChange={(e) =>
                        change({
                          selected_participant_ids: e.target.checked
                            ? [...selected, p.id]
                            : [...selected].filter((id) => id !== p.id),
                        })
                      }
                    />
                    <span>{p.name}</span>
                  </label>
                ))
              ) : (
                <p className="text-sm text-slate-500">
                  No participants with recorded Male gender are currently available.
                </p>
              )}
            </div>
          </div>
          <div>
            <h3 className="font-extrabold">Session schedule</h3>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <TimeField
                label="Start time"
                value={settings.start_time}
                change={(value) => change({ start_time: value })}
              />
              <label className="text-sm font-bold">
                Session duration (minutes)
                <input
                  className="input mt-1"
                  type="number"
                  min="1"
                  max="240"
                  value={String(settings.session_duration_minutes ?? 20)}
                  onChange={(e) =>
                    change({ session_duration_minutes: Number(e.target.value) })
                  }
                />
              </label>
              <TimeField
                label="Friday prayer start"
                value={settings.prayer_deadline}
                change={(value) => change({ prayer_deadline: value })}
              />
              <TimeField
                label="Post-prayer resume time"
                value={settings.resume_time}
                change={(value) => change({ resume_time: value })}
              />
              <TimeField label="Fixed final end time (optional)" value={settings.end_time??""} change={value=>change({end_time:value||null})}/>
            </div>
            <div
              className="mt-4 rounded-xl bg-blue-50 p-3 text-sm text-blue-900"
            >
              <b>
                {available} complete slots per faculty · {capacity} total
                pre-prayer slots
              </b>
              <p>
                {selected.size} selected
                {selected.size>capacity?` · remaining appointments continue from ${settings.resume_time} after prayer`:" · appointments may run before or after the protected break"}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
function TimeField({
  label,
  value,
  change,
}: {
  label: string;
  value: string;
  change: (value: string) => void;
}) {
  return (
    <label className="text-sm font-bold">
      {label}
      <input
        className="input mt-1"
        type="time"
        value={value ?? ""}
        onChange={(e) => change(e.target.value)}
      />
    </label>
  );
}
function TopBack({ onClick, step }: { onClick: () => void; step: string }) {
  return (
    <div className="mb-5 flex justify-between">
      <button className="btn btn-outline" onClick={onClick}>
        <ArrowLeft size={17} />
        Back
      </button>
      <b className="text-sm text-slate-500">{step}</b>
    </div>
  );
}
function Next({
  onClick,
  label,
  disabled = false,
}: {
  onClick: () => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <div className="mt-6 flex justify-end">
      <button className="btn btn-primary" disabled={disabled} onClick={onClick}>
        {label}
        {disabled ? (
          <RefreshCw className="animate-spin" size={17} />
        ) : (
          <ArrowRight size={17} />
        )}
      </button>
    </div>
  );
}
function Review({
  records,
  people,
  resolve,
}: {
  records: ChemistryRecord[];
  people: Participant[];
  resolve: (r: ChemistryRecord, id: string) => void;
}) {
  return (
    <div className="card mt-5 p-6">
      <h2 className="text-xl font-extrabold">
        Chemistry matches requiring review
      </h2>
      <p className="text-sm text-slate-500">
        Choose the correct new hire. Ambiguous names are never merged
        automatically.
      </p>
      {records.map((r) => (
        <label
          className="mt-4 grid gap-2 sm:grid-cols-2 sm:items-center"
          key={r.source_name}
        >
          <span>
            <b>{r.source_name}</b> · {r.primary} / {r.secondary}
          </span>
          <select
            className="input"
            value=""
            onChange={(e) => resolve(r, e.target.value)}
          >
            <option value="">Choose participant…</option>
            {people.map((p) => (
              <option value={p.id} key={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
      ))}
    </div>
  );
}
function ParticipantTable({
  people,
  edit,
  add,
  remove,
  resize,
  clear,
  universities,
}: {
  people: Participant[];
  edit: (id: string, f: string, v: string) => void;
  add: () => void;
  remove: (id: string) => void;
  resize: (n: number) => void;
  clear: () => void;
  universities: University[];
}) {
  const [draft, setDraft] = useState(String(people.length));
  useEffect(() => setDraft(String(people.length)), [people.length]);
  return (
    <div className="card mt-5 overflow-visible">
      <div className="flex items-center justify-between border-b p-5">
        <div>
          <h2 className="font-extrabold">New hire preview</h2>
          <p className="text-sm text-slate-500">{people.length} records</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <input
            aria-label="Number of participants"
            className="input w-24"
            type="number"
            min="1"
            max="60"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <button
            className="btn btn-outline"
            disabled={Number(draft) === people.length}
            onClick={() => resize(Number(draft))}
          >
            Apply Count
          </button>
          <button className="btn btn-outline" onClick={add}>
            <Plus size={16} />
            Add Participant
          </button>
          <button
            className="btn border border-red-200 bg-red-50 text-red-700"
            onClick={clear}
          >
            Clear All
          </button>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[1100px]">
          <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
            <tr>
              {[
                "#",
                "Candidate Name",
                "Gender",
                "University",
                "L3 Offering",
                "Primary",
                "Secondary",
                "",
              ].map((x) => (
                <th className="p-3" key={x}>
                  {x}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {people.map((p, i) => (
              <tr className="border-t align-top" key={p.id}>
                <td className="p-3">{i + 1}</td>
                <td className="p-2">
                  <input
                    className="input"
                    value={p.name}
                    onChange={(e) => edit(p.id, "name", e.target.value)}
                  />
                </td>
                <td className="p-2">
                  <select
                    className="input"
                    value={String(p.attributes.Gender || "")}
                    onChange={(e) => edit(p.id, "Gender", e.target.value)}
                  >
                    <option value="">Select</option>
                    <option>Male</option>
                    <option>Female</option>
                  </select>
                </td>
                <td className="p-2">
                  <UniversityAutocomplete
                    label={`University ${i + 1}`}
                    value={String(p.attributes.University || "")}
                    onChange={(v) => edit(p.id, "University", v)}
                    directory={universities}
                    customValues={[]}
                  />
                </td>
                <td className="p-2">
                  <input
                    className="input"
                    value={String(p.attributes["L3 Offering"] || "")}
                    onChange={(e) => edit(p.id, "L3 Offering", e.target.value)}
                  />
                </td>
                <td className="p-2">
                  <ChemistrySelect
                    value={String(p.attributes["Primary Chemistry"] || "")}
                    change={(v) => edit(p.id, "Primary Chemistry", v)}
                  />
                </td>
                <td className="p-2">
                  <ChemistrySelect
                    value={String(p.attributes["Secondary Chemistry"] || "")}
                    change={(v) => edit(p.id, "Secondary Chemistry", v)}
                  />
                </td>
                <td className="p-3">
                  <button className="text-red-600" onClick={() => remove(p.id)}>
                    <Trash2 size={17} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
function SizeCard({
  activity,
  count,
  change,
}: {
  activity: Configuration["activities"][number];
  count: number;
  change: (v: number) => void;
}) {
  return (
    <article className="card p-6">
      <h2 className="text-xl font-extrabold">{activity.name}</h2>
      <p className="mt-1 text-sm text-slate-500">
        Preferred maximum group size
      </p>
      <div className="mt-6 flex items-center justify-center gap-5">
        <button
          className="grid h-12 w-12 place-items-center rounded-xl border text-2xl disabled:opacity-30"
          disabled={activity.value <= 2}
          onClick={() => change(activity.value - 1)}
        >
          −
        </button>
        <b className="w-12 text-center text-2xl">{activity.value}</b>
        <button
          className="grid h-12 w-12 place-items-center rounded-xl border text-2xl disabled:opacity-30"
          disabled={activity.value >= 12}
          onClick={() => change(activity.value + 1)}
        >
          +
        </button>
      </div>
      <div className="mt-5 rounded-xl bg-slate-50 p-4 text-sm">
        <b>{count} balanced groups</b>
      </div>
    </article>
  );
}
function EditPanel({
  activity,
  people,
  support,
  faculty,
  chemistryEnabled,
  a,
  b,
  setA,
  setB,
  swap,
}: {
  activity: NonNullable<Allocation>["activities"][number];
  people: Record<string, Participant>;
  support: Record<string, SupportMember>;
  faculty: FacultyMember[];
  chemistryEnabled: boolean;
  a: string;
  b: string;
  setA: (x: string) => void;
  setB: (x: string) => void;
  swap: () => void;
}) {
  const options = activity.groups.flatMap((g) =>
    g.participant_ids.map((id) => ({
      id,
      label: faculty.find(member=>member.id===id)?`${faculty.find(member=>member.id===id)?.name} · Faculty · ${g.name}`:editLabel(id, g.name, people, support, chemistryEnabled),
    })),
  );
  return (
    <div className="results-switch-panel">
      <h2 className="font-semibold">Edit {activity.activity_name}</h2>
      <p className="text-sm text-slate-500">
        {activity.activity_id === "reflection"
          ? "Select any two participants to exchange their existing faculty and appointment slots."
          : "Select two people to switch assignments. Structural constraints are validated before saving."}
      </p>
      <div className="mt-4 grid gap-3 md:grid-cols-[1fr_1fr_auto]">
        <select
          className="input"
          aria-label="First participant to switch"
          value={a ?? ""}
          onChange={(e) => setA(e.target.value)}
        >
          <option value="">First person…</option>
          {options.map((x) => (
            <option key={x.id} value={x.id}>
              {x.label}
            </option>
          ))}
        </select>
        <select
          className="input"
          aria-label="Second participant to switch"
          value={b ?? ""}
          onChange={(e) => setB(e.target.value)}
        >
          <option value="">Second person…</option>
          {options.map((x) => (
            <option key={x.id} value={x.id}>
              {x.label}
            </option>
          ))}
        </select>
        <button
          className="btn btn-primary"
          disabled={!a || !b || a === b}
          title={!a||!b?"Choose two participants to enable switching":a===b?"Choose two different participants":"Exchange these two assignments"}
          onClick={swap}
        >
          Switch Participants
        </button>
      </div>
    </div>
  );
}
function AllocationCards({
  activity,people,support,faculty,chemistryEnabled,reflectionSettings,editable=false,selectedIds=[],
}: {
  activity: Allocation["activities"][number] | undefined;
  people: Record<string,Participant>;
  support: Record<string,SupportMember>;
  faculty: FacultyMember[];
  chemistryEnabled:boolean;
  reflectionSettings:Configuration["reflection_settings"];
  editable?:boolean;
  selectedIds?:string[];
}) {
  if(!activity)return null;
  const sessions=activity.sessions??[];
  const hotelSummary=activity.activity_id==="hotel"?hotelRoomSummary(activity.groups,people,support,faculty):null;
  if(activity.activity_id==="reflection"&&reflectionSettings.enabled&&sessions.length)
    return <>
      <ReflectionSummary activity={activity}/>
      <ReflectionSchedule activity={activity} people={people} faculty={faculty} chemistryEnabled={chemistryEnabled} settings={reflectionSettings} editable={editable} selectedIds={selectedIds}/>
    </>;
  return <>
    {activity.activity_id==="reflection"&&<ReflectionSummary activity={activity}/>}
    {hotelSummary&&<>
      <HotelResultsSummary summary={hotelSummary}/>
      {hotelSummary.new_hire_single>0&&<p className="results-notice" role="status"><AlertCircle size={17} aria-hidden="true"/><span>{hotelSummary.new_hire_single} new hire(s) require a single room. Review compatible same-gender Analyst Support availability or reserve these single rooms.</span></p>}
    </>}
    {activity.activity_id!=="hotel"&&activity.warnings?.map(warning=><p className="results-notice" role="status" key={warning}><AlertCircle size={17} aria-hidden="true"/>{warning}</p>)}
    <div className={`results-group-grid ${hotelSummary?"results-room-grid":""}`}>
      {activity.groups.map((group,groupIndex)=>{
        const room=hotelSummary?hotelRoomAppearance(group.participant_ids,people,support):null;
        return <DroppableGroup groupId={group.id} editable={editable} key={group.id}>
          <AllocationGroupCard title={group.name} count={group.participant_ids.length} index={groupIndex+1} activityId={activity.activity_id} room={room}>
            <ol className="allocation-participant-list">
              {group.participant_ids.map((id,index)=>{
                const person=people[id],helper=support[id],facultyMember=faculty.find(member=>member.id===id);
                const gender=person?.attributes.Gender??helper?.gender;
                const selected=editable&&selectedIds.includes(id);
                return <li className={`result-person-row result-record ${room?"":genderRowClass(gender)} ${helper?"result-record-staff":""} ${selected?"is-selected":""}`} data-recorded-gender={String(gender??"unknown")} data-selected={selected||undefined} key={id}>
                  <EditablePerson participantId={id} groupId={group.id} editable={editable}>
                    <ParticipantRow index={index+1} name={person?.name||helper?.name||facultyMember?.name||id} gender={gender} category={person?canonicalCategory(person.attributes["University Category"]):undefined} role={helper?.category??(facultyMember?"Faculty":hotelSummary?"New hire":undefined)} person={person} offering={person?standardOffering(person.attributes["L3 Offering"]):undefined} chemistryEnabled={chemistryEnabled} selected={selected}/>
                  </EditablePerson>
                </li>;
              })}
            </ol>
          </AllocationGroupCard>
        </DroppableGroup>;
      })}
    </div>
  </>;
}
function ReflectionSchedule({
  activity,
  people,
  faculty,
  chemistryEnabled,
  settings,
  editable = false,
  selectedIds = [],
}: {
  activity: Allocation["activities"][number];
  people: Record<string, Participant>;
  faculty: FacultyMember[];
  chemistryEnabled: boolean;
  settings: Configuration["reflection_settings"];
  editable?: boolean;
  selectedIds?: string[];
}) {
  const sessions = activity.sessions ?? [];
  return (
    <div className="reflection-schedules">
      {faculty.map((assigned) => {
        const assignedSessions = sessions
          .filter((session) => session.faculty_id === assigned.id)
          .sort(
            (a, b) => clockMinutes(a.start_time) - clockMinutes(b.start_time),
          );
        return (
          <DroppableGroup
            groupId={assigned.id}
            editable={editable}
            key={assigned.id}
          >
            <section className="faculty-schedule">
              <FacultyScheduleHeader name={assigned.name}/>
              <div className="reflection-table-container">
                <table className="reflection-table" aria-label={`Appointments with ${assigned.name}`}>
                  <thead>
                    <tr>
                      {[
                        "#",
                        "Time",
                        "Participant",
                        "University",
                        "L3 Offering",
                        "Business Chemistry",
                        "Match",
                        "Prayer Status",
                      ].map((column) => (
                        <th
                          className="reflection-column-heading"
                          scope="col"
                          key={column}
                        >
                          {column}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {assignedSessions.map((session, index) => {
                      const person = people[session.participant_id],
                        university =
                          String(person?.attributes.University ?? "").trim() ||
                          "University not provided",
                        offering =
                          standardOffering(person?.attributes["L3 Offering"]) ||
                          "Offering not provided",
                        primary = String(
                          person?.attributes["Primary Chemistry"] ?? "",
                        ).trim(),
                        secondary = String(
                          person?.attributes["Secondary Chemistry"] ?? "",
                        ).trim(),
                        accommodated =
                          settings.selected_participant_ids.includes(
                            session.participant_id,
                          );
                      return (
                        <EditableTableRow
                          participantId={session.participant_id}
                          groupId={assigned.id}
                          index={index + 1}
                          editable={editable}
                          gender={person?.attributes.Gender}
                          selected={editable&&selectedIds.includes(session.participant_id)}
                          key={session.participant_id}
                        >
                          <td data-label="Time" className="reflection-time-cell">
                            <span className="session-time">{session.start_time}<span className="session-time-divider">–</span>{session.end_time}</span>
                          </td>
                          <td data-label="Participant" className="reflection-name-cell">
                            <ParticipantIdentity name={person?.name||session.participant_id} gender={person?.attributes.Gender} category={canonicalCategory(person?.attributes["University Category"])}/>
                          </td>
                          <td data-label="University" className="reflection-university-cell">
                            <span title={university}>
                              {university}
                            </span>
                          </td>
                          <td data-label="L3 Offering" className="reflection-offering-cell">
                            <span title={offering}>
                              {offering}
                            </span>
                          </td>
                          <td data-label="Business Chemistry" className={chemistryEnabled?"reflection-chemistry-cell":"reflection-chemistry-cell is-empty"}>
                            {chemistryEnabled && primary && secondary ? (
                              <div className="reflection-chemistry">
                                <span className="chemistry-segment">
                                  P: {primary}
                                </span>
                                <span className="chemistry-segment">
                                  S: {secondary}
                                </span>
                              </div>
                            ) : (
                              <span className="text-slate-400">—</span>
                            )}
                          </td>
                          <td data-label="Match">
                            <span
                              className={`schedule-status ${session.offering_match ? "status-match" : "status-review"}`}
                            >
                              {session.offering_match ? "Match" : "Mismatch"}
                            </span>
                          </td>
                          <td data-label="Prayer Status">
                            {accommodated ? (
                              <span className="schedule-status status-prayer">
                                {session.before_prayer?"Before prayer":"After prayer"}
                              </span>
                            ) : (
                              <span className="text-slate-400">—</span>
                            )}
                          </td>
                        </EditableTableRow>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          </DroppableGroup>
        );
      })}
    </div>
  );
}
function clockMinutes(value: string) {
  const match = value.match(/^(\d{1,2}):(\d{2})\s*(AM|PM)$/i);
  if (!match) {const clock=value.match(/^(\d{1,2}):(\d{2})$/);return clock?Number(clock[1])*60+Number(clock[2]):Number.MAX_SAFE_INTEGER;}
  let hour = Number(match[1]) % 12;
  if (match[3].toUpperCase() === "PM") hour += 12;
  return hour * 60 + Number(match[2]);
}
function DroppableGroup({
  groupId,
  editable,
  children,
}: {
  groupId: string;
  editable: boolean;
  children: ReactNode;
}) {
  const { setNodeRef, isOver } = useDroppable({
    id: `group:${groupId}`,
    disabled: !editable,
  });
  return (
    <div
      ref={setNodeRef}
      className={`result-group-drop ${isOver ? "is-over" : ""}`}
    >
      {children}
    </div>
  );
}
function EditablePerson({
  participantId,
  groupId,
  editable,
  children,
}: {
  participantId: string;
  groupId: string;
  editable: boolean;
  children: ReactNode;
}) {
  const drag = useDraggable({
      id: `drag:item:${participantId}`,
      disabled: !editable,
    }),
    drop = useDroppable({
      id: `person:${groupId}:${participantId}`,
      disabled: !editable,
    });
  const setRef = (node: HTMLElement | null) => {
    drag.setNodeRef(node);
    drop.setNodeRef(node);
  };
  return (
    <div
      ref={setRef}
      className={`editable-person ${drop.isOver ? "is-over" : ""} ${drag.isDragging?"is-dragging":""}`}
      style={{
        transform: CSS.Translate.toString(drag.transform),
        opacity: 1,
        zIndex: drag.isDragging ? 50 : undefined,
      }}
    >
      {editable && (
        <button
          className="result-drag-handle"
          aria-label={`Drag participant ${participantId}`}
          {...drag.listeners}
          {...drag.attributes}
        >
          <GripVertical size={16} aria-hidden="true"/>
        </button>
      )}
      {children}
    </div>
  );
}
function EditableTableRow({
  participantId,
  groupId,
  index,
  editable,
  gender,
  selected = false,
  children,
}: {
  participantId: string;
  groupId: string;
  index: number;
  editable: boolean;
  gender?: unknown;
  selected?: boolean;
  children: ReactNode;
}) {
  const drag = useDraggable({
      id: `drag:item:${participantId}`,
      disabled: !editable,
    }),
    drop = useDroppable({
      id: `person:${groupId}:${participantId}`,
      disabled: !editable,
    });
  const setRef = (node: HTMLTableRowElement | null) => {
    drag.setNodeRef(node);
    drop.setNodeRef(node);
  };
  return (
    <tr
      ref={setRef}
      className={`result-person-row ${genderRowClass(gender)} ${drop.isOver ? "is-over" : ""} ${drag.isDragging?"is-dragging":""} ${selected?"is-selected":""}`}
      data-recorded-gender={String(gender??"unknown")}
      data-selected={selected||undefined}
      style={{
        transform: CSS.Translate.toString(drag.transform),
        opacity: 1,
      }}
    >
      <td data-label="#" className="reflection-index-cell">
        <span className="inline-flex items-center gap-1">
          {index}
          {editable && (
            <button
              className="result-drag-handle"
              aria-label={`Drag participant ${participantId}`}
              {...drag.listeners}
              {...drag.attributes}
            >
              <GripVertical size={15} aria-hidden="true"/>
            </button>
          )}
        </span>
      </td>
      {children}
    </tr>
  );
}
function editLabel(
  id: string,
  group: string,
  people: Record<string, Participant>,
  support: Record<string, SupportMember>,
  chemistryEnabled: boolean,
) {
  const person = people[id];
  if (!person) return `${support[id]?.name || id} · ${support[id]?.category || "Support category required"} · ${group}`;
  const university =
      String(person.attributes.University ?? "").trim() ||
      "University not provided",
    offering =
      standardOffering(person.attributes["L3 Offering"]) ||
      "Offering not provided";
  const chemistry = chemistryEnabled
    ? ` · Primary: ${String(person.attributes["Primary Chemistry"] ?? "").trim() || "missing"} · Secondary: ${String(person.attributes["Secondary Chemistry"] ?? "").trim() || "missing"}`
    : "";
  return `${person.name} · ${university} · ${offering}${chemistry} — ${group}`;
}
function ChemistrySelect({
  value,
  change,
}: {
  value: string;
  change: (v: string) => void;
}) {
  return (
    <select
      className="input"
      value={value ?? ""}
      onChange={(e) => change(e.target.value)}
    >
      <option value="">Select</option>
      {["Pioneer", "Driver", "Guardian", "Integrator"].map((x) => (
        <option key={x}>{x}</option>
      ))}
    </select>
  );
}
function message(e: unknown) {
  return e instanceof Error ? e.message : String(e);
}
