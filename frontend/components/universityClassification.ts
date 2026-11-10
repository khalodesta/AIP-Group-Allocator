import type { CustomUniversity, Participant, UniversityCategory } from "../types";
import type { University } from "./UniversityAutocomplete";

export type PendingUniversity = Omit<CustomUniversity, "category">;
export const UNIVERSITY_CATEGORIES: Record<UniversityCategory, string> = {
  public: "Public", private: "Private",
};
export const normalizeUniversityKey = (value: string) => value.toLocaleLowerCase().normalize("NFKD")
  .replace(/[أإآٱ]/g, "ا").replace(/ى/g, "ي").replace(/ة/g, "ه").replace(/ؤ/g, "و").replace(/ئ/g, "ي")
  .replace(/[ًٌٍَُِّْـ]/g, "").replace(/[^\p{L}\p{N}\s]/gu, " ").replace(/\s+/g, " ").trim();
export function canonicalCategory(value: unknown): UniversityCategory | undefined {
  if (value === "public" || value === "public_technological") return "public";
  if (value === "private" || value === "private_technological") return "private";
  return undefined;
}
export function mergedUniversityDirectory(directory: University[], custom: CustomUniversity[], pending: PendingUniversity[] = []): University[] {
  const result = new Map(directory.map(u => [u.id, u]));
  for (const item of [...pending, ...custom]) {
    const old = result.get(item.id), category = canonicalCategory("category" in item ? item.category : undefined);
    result.set(item.id, {
      id:item.id, official_english_name:old?.official_english_name ?? item.name,
      official_arabic_name:old?.official_arabic_name ?? null,
      abbreviations:old?.abbreviations ?? [], english_variations:[...(old?.english_variations ?? []), item.name, ...item.aliases],
      arabic_variations:old?.arabic_variations ?? [], category:old?.category ?? "",
      diversity_category:category ?? old?.diversity_category ?? null,
    });
  }
  return [...result.values()];
}
export function universityIdentity(value: string, directory: University[]) {
  const key=normalizeUniversityKey(value);
  return directory.find(u => [u.official_english_name,u.official_arabic_name,...u.abbreviations,...u.english_variations,...u.arabic_variations]
    .some(name => name && normalizeUniversityKey(name) === key));
}
export function classifyUniversity(value: string, directory: University[], custom: CustomUniversity[]): UniversityCategory | undefined {
  const key=normalizeUniversityKey(value), official=universityIdentity(value,directory);
  const correction=custom.find(item => item.id===official?.id || [item.name,...item.aliases].some(alias=>normalizeUniversityKey(alias)===key));
  return canonicalCategory(correction?.category) ?? canonicalCategory(official?.diversity_category ?? official?.category);
}
export function classifiedParticipants(people: Participant[], directory: University[], custom: CustomUniversity[]): Participant[] {
  const merged=mergedUniversityDirectory(directory,custom);
  const confirmed = new Map<string, Set<UniversityCategory>>();
  // A confirmed cohort mapping applies to every normalized alias of its institution.
  for (const person of people) {
    const value=String(person.attributes.University ?? ""), identity=universityIdentity(value,merged);
    const category=classifyUniversity(value,directory,custom) ?? canonicalCategory(person.attributes["University Category"]);
    if (category) {
      const id=identity?.id ?? `custom:${normalizeUniversityKey(value)}`;
      if(!confirmed.has(id))confirmed.set(id,new Set());
      confirmed.get(id)!.add(category);
    }
  }
  return people.map(person => {
    const name=String(person.attributes.University ?? ""), identity=universityIdentity(name,merged);
    const choices=confirmed.get(identity?.id ?? `custom:${normalizeUniversityKey(name)}`);
    const category=classifyUniversity(name,directory,custom) ?? (choices?.size===1?[...choices][0]:undefined);
    return {...person,attributes:{...person.attributes,University:identity?.official_english_name ?? name,"University Category":category ?? null}};
  });
}
function directoryEntries(value: unknown): unknown[] {
  const entries=Array.isArray(value)?value:(value && typeof value==="object" && "universities" in value?(value as {universities:unknown}).universities:null);
  if (!Array.isArray(entries)) throw new Error("Choose a university directory JSON file containing a universities list.");
  if (entries.length>2000) throw new Error("The custom directory may contain at most 2,000 universities.");
  return entries;
}
function validateEntries(entries: unknown[]): (PendingUniversity & {category:unknown})[] {
  const ids=new Set<string>(), aliases=new Map<string,string>();
  return entries.map(item=>{
    if (!item || typeof item!=="object" || !("id" in item) || typeof item.id!=="string" || !item.id.trim() || !("name" in item) || typeof item.name!=="string" || !item.name.trim() || !("aliases" in item) || !Array.isArray(item.aliases) || item.aliases.some((alias:unknown)=>typeof alias!=="string")) throw new Error("Each university needs an ID, name, and aliases list.");
    const id=item.id.trim(), name=item.name.trim(), names=item.aliases as string[];
    if (ids.has(id)) throw new Error("The directory contains duplicate university IDs.");
    ids.add(id);
    for (const alias of [name,...names]) {
      const key=normalizeUniversityKey(alias), existing=aliases.get(key);
      if (existing && existing!==id) throw new Error(`The alias “${alias}” is assigned to more than one university.`);
      if (key) aliases.set(key,id);
    }
    return {id,name,aliases:names.map(alias=>alias.trim()).filter(Boolean),category:"category" in item?item.category:undefined};
  });
}
export function parseCustomDirectory(value: unknown): CustomUniversity[] {
  const entries=validateEntries(directoryEntries(value));
  const invalid=entries.filter(item=>item.category!=="public"&&item.category!=="private");
  if (invalid.length) throw new Error(`Public or Private classification required: ${invalid.map(item=>item.name).join(", ")}. Review these entries and confirm one of the two grouping categories before importing. No category was guessed.`);
  return entries.map(item=>({...item,category:item.category as UniversityCategory}));
}
export function migrateCustomDirectory(value: unknown): {universities:CustomUniversity[];pending:PendingUniversity[]} {
  const entries=validateEntries(directoryEntries(value));
  const universities:CustomUniversity[]=[], pendingById=new Map<string,PendingUniversity>();
  const savedPending=value&&typeof value==="object"&&"pending_review" in value?(value as {pending_review:unknown}).pending_review:[];
  if (Array.isArray(savedPending)) for (const {id,name,aliases} of validateEntries(savedPending)) pendingById.set(id,{id,name,aliases});
  for (const {id,name,aliases,category} of entries) {
    if (category==="public"||category==="private") {universities.push({id,name,aliases,category});pendingById.delete(id);}
    else pendingById.set(id,{id,name,aliases});
  }
  const pending=[...pendingById.values()];
  validateEntries([...universities,...pending]);
  return {universities,pending};
}
