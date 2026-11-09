import type { CustomUniversity, Participant, UniversityCategory } from "../types";
import type { University } from "./UniversityAutocomplete";

export const UNIVERSITY_CATEGORIES: Record<UniversityCategory, string> = {
  public: "Public", private: "Private", national: "National / Ahleya",
  international: "International / Foreign Branch", other: "Other / Needs Review",
};
export const normalizeUniversityKey = (value: string) => value.toLocaleLowerCase().normalize("NFKD")
  .replace(/[أإآٱ]/g, "ا").replace(/ى/g, "ي").replace(/ة/g, "ه").replace(/ؤ/g, "و").replace(/ئ/g, "ي")
  .replace(/[ًٌٍَُِّْـ]/g, "").replace(/[^\p{L}\p{N}\s]/gu, " ").replace(/\s+/g, " ").trim();
export function canonicalCategory(value: unknown): UniversityCategory | undefined {
  const key = String(value ?? "");
  if (Object.prototype.hasOwnProperty.call(UNIVERSITY_CATEGORIES,key)) return key as UniversityCategory;
  return ({public_technological:"public", private_technological:"private", national_ahlia:"national", foreign_branch:"international", international_agreement:"international", framework_agreement:"international"} as Record<string,UniversityCategory>)[key];
}
export function mergedUniversityDirectory(directory: University[], custom: CustomUniversity[]): University[] {
  const result = new Map(directory.map(u => [u.id, u]));
  for (const item of custom) {
    const old = result.get(item.id);
    result.set(item.id, {
      id:item.id, official_english_name:old?.official_english_name ?? item.name,
      official_arabic_name:old?.official_arabic_name ?? null,
      abbreviations:old?.abbreviations ?? [], english_variations:[...(old?.english_variations ?? []), item.name, ...item.aliases],
      arabic_variations:old?.arabic_variations ?? [], category:item.category, diversity_category:item.category,
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
  return correction?.category ?? canonicalCategory(official?.diversity_category ?? official?.category);
}
export function classifiedParticipants(people: Participant[], directory: University[], custom: CustomUniversity[]): Participant[] {
  return people.map(person => {
    const name=String(person.attributes.University ?? ""), identity=universityIdentity(name,mergedUniversityDirectory(directory,custom));
    return {...person,attributes:{...person.attributes,University:identity?.official_english_name ?? name,"University Category":classifyUniversity(name,directory,custom) ?? canonicalCategory(person.attributes["University Category"]) ?? null}};
  });
}
export function parseCustomDirectory(value: unknown): CustomUniversity[] {
  const entries=Array.isArray(value)?value:(value && typeof value==="object" && "universities" in value?(value as {universities:unknown}).universities:null);
  if (!Array.isArray(entries)) throw new Error("Choose a university directory JSON file containing a universities list.");
  if (entries.length>2000) throw new Error("The custom directory may contain at most 2,000 universities.");
  const ids=new Set<string>(), aliases=new Map<string,string>();
  return entries.map(item=>{
    if (!item || typeof item!=="object" || typeof item.id!=="string" || !item.id.trim() || typeof item.name!=="string" || !item.name.trim() || !Array.isArray(item.aliases) || item.aliases.some((alias:unknown)=>typeof alias!=="string") || !Object.prototype.hasOwnProperty.call(UNIVERSITY_CATEGORIES,item.category)) throw new Error("Each university needs an ID, name, aliases list, and a supported category.");
    if (ids.has(item.id.trim())) throw new Error("The directory contains duplicate university IDs.");
    ids.add(item.id.trim());
    for (const alias of [item.name,...item.aliases]) {
      const key=normalizeUniversityKey(alias), existing=aliases.get(key);
      if (existing && existing!==item.id) throw new Error(`The alias “${alias}” is assigned to more than one university.`);
      if (key) aliases.set(key,item.id);
    }
    return {id:item.id.trim(),name:item.name.trim(),aliases:item.aliases.map((alias:string)=>alias.trim()).filter(Boolean),category:item.category};
  });
}
