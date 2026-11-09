"""One-time generator for the checked-in university_directory.json."""
import json, re
from pathlib import Path

SOURCE="https://sis.gov.eg/en/egyptians-abroad-portal/education/university-education/updated-list-of-accredited-higher-education-institutions/"
VERIFIED="2026-11-03"
# Keep the official legal classification and the five UI diversity categories
# separate: an institution established by international agreement can be private.
CATEGORY_GROUPS={"public":"public","public_technological":"public","private":"private","private_technological":"private","national_ahlia":"national","international_agreement":"international","framework_agreement":"international","foreign_branch":"international","special_nature":"other","government_supervision":"other"}
groups={
"public":["Cairo University","Alexandria University","Ain Shams University","Assiut University","Tanta University","Mansoura University","Zagazig University","Capital University","Minia University","Menoufia University","Suez Canal University","South Valley University","Banha University","Fayoum University","Beni Suef University","Kafrelsheikh University","Sohag University","Port Said University","Damanhour University","Aswan University","Damietta University","Sadat City University","Suez University","Arish University","New Valley University","Matrouh University","Luxor University","Hurghada University"],
"private":["6th October University","October University for Modern Sciences and Arts","Misr University for Science and Technology","Misr International University","German University in Cairo","Al-Ahram Canadian University","The British University in Egypt","Modern University for Technology and Information","Sinai University","Pharos University in Alexandria","Al-Nahda University in Beni Suef","Future University","Egyptian Russian University","Delta University for Science and Technology in Gamasa","Heliopolis University","New Giza University","Deraya University in Minya","Badr University","Horus University","Egyptian Chinese University","Merritt University","Sphinx University","Peace University (El Salam University)","Badr University in Assiut","New Salhia University","El Haia University","May University","El Riada University for Science and Technology - Sadat City","Innovation University","City University of Cairo","Rasheed University","Badya University","Wady El Nil Fayoum University","Lotus University in Minia","Obour University for Modern Sciences and Technology","Memphis University","East Capital University","Egyptian University in Alamein","New Heliopolis University"],
"national_ahlia":["King Salman International University","El Alamein International University","Galala University","New Mansoura University","The Egyptian E-learning National University","Nile National University","The French University in Egypt","Egypt University for Informatics","Helwan National University","Mansoura National University","Banha National University","Menoufia National University","Beni Suef National University","Assiut National University","South Valley National University","Minia National University","East Port Said National University","Alexandria National University","Zagazig National University","New Ismailia National University","Suez National University","Damanhour National University","Cairo National University","Ain Shams National University","Sohag National University","Kafrelsheikh National University","New Valley National University","Fayoum National University","Tanta National University","Luxor National University","Damietta National University","Sadat City National University"],
"special_nature":["Zewail City of Science and Technology"],
"international_agreement":["The American University in Cairo","Egypt-Japan University of Science and Technology","German International University in the Administrative Capital","University of ESLSCA","Technische Universität Berlin - El Gouna Campus","Senghor University"],
"framework_agreement":["Arab Academy for Science, Technology and Maritime Transport","Arab Open University"],
"foreign_branch":["University of Prince Edward Island - Cairo Branch","Coventry University - Cairo Branch","NOVA University Lisbon - Cairo Branch","University of Hertfordshire - Egypt Branch","University of London - Cairo Branch","University of Central Lancashire - Cairo Branch","University of East London - Cairo Branch","Kazan Federal University - Cairo Branch","Saint Petersburg State University - Cairo Branch","Anglia Ruskin University - Egypt Branch"],
"public_technological":["New Cairo Technological University","Delta Technological University","Beni Suef Technological University","New Assiut Technological University","Borg Al Arab Technological University","Thebes Technological University","6th October Technological University","Samanoud Technological University","East Port Said Technological University","Helwan Technological University","Fayoum Technological University","Assiut Technological University"],
"private_technological":["El Sewedy University of Technology","Saxony Egypt University for Applied Sciences and Technology"],
"government_supervision":["Sadat Academy for Administrative Sciences"],
}
meta={
"Cairo University":("جامعة القاهرة",["CU"],[],["جامعه القاهره"]),
"Alexandria University":("جامعة الإسكندرية",[],[],["جامعه الاسكندريه"]),
"Ain Shams University":("جامعة عين شمس",["ASU"],[],["جامعه عين شمس"]),
"Assiut University":("جامعة أسيوط",[],[],["جامعه اسيوط"]),
"Tanta University":("جامعة طنطا",[],[],[]),
"Mansoura University":("جامعة المنصورة",["MU"],[],["جامعه المنصوره"]),
"Zagazig University":("جامعة الزقازيق",[],[],[]),
"Capital University":("جامعة العاصمة",[],["Helwan University","Capital University","Capital-Helwan University"],["جامعة حلوان","جامعه العاصمه","جامعه حلوان"]),
"Minia University":("جامعة المنيا",[],["Menia University"],[]),
"Menoufia University":("جامعة المنوفية",[],["Minufiya University"],[]),
"Suez Canal University":("جامعة قناة السويس",["SCU"],[],[]),
"South Valley University":("جامعة قنا",["SVU"],["Qena University"],["جامعه جنوب الوادي"]),
"Banha University":("جامعة بنها",[],["Benha University"],[]),
"Fayoum University":("جامعة الفيوم",[],[],[]),
"Beni Suef University":("جامعة بني سويف",[],["Bani Suef University"],[]),
"Kafrelsheikh University":("جامعة كفر الشيخ",[],["Kafr El Sheikh University"],[]),
"Sohag University":("جامعة سوهاج",[],[],[]),
"Port Said University":("جامعة بورسعيد",[],[],[]),
"Damanhour University":("جامعة دمنهور",[],[],[]),
"Aswan University":("جامعة أسوان",[],[],[]),
"Damietta University":("جامعة دمياط",[],[],[]),
"Sadat City University":("جامعة مدينة السادات",[],[],[]),
"Suez University":("جامعة السويس",[],[],[]),
"Arish University":("جامعة العريش",[],[],[]),
"New Valley University":("جامعة الوادي الجديد",[],[],[]),
"Matrouh University":("جامعة مطروح",[],[],[]),
"Luxor University":("جامعة الأقصر",[],[],[]),
"Hurghada University":("جامعة الغردقة",[],[],[]),
"German University in Cairo":("الجامعة الألمانية بالقاهرة",["GUC"],["German University Cairo"],["الجامعه الالمانيه بالقاهره"]),
"The American University in Cairo":("الجامعة الأمريكية بالقاهرة",["AUC"],["American University in Cairo"],["الجامعه الامريكيه بالقاهره"]),
"Misr International University":("جامعة مصر الدولية",["MIU"],[],[]),
"Mansoura National University":("جامعة المنصورة الأهلية",["MNU"],["Mansoura Ahlia University"],["جامعه المنصوره الاهليه"]),
"Cairo National University":("جامعة القاهرة الأهلية",["CNU"],["Cairo Ahlia University"],["جامعه القاهره الاهليه"]),
"Helwan National University":("جامعة حلوان الأهلية",["HNU"],["Helwan Ahlia University","Helwan Ahleya University"],["جامعه حلوان الاهليه"]),
"October University for Modern Sciences and Arts":("جامعة أكتوبر للعلوم الحديثة والآداب",["MSA"],["MSA University"],[]),
"Misr University for Science and Technology":("جامعة مصر للعلوم والتكنولوجيا",["MUST"],[],[]),
"The British University in Egypt":("الجامعة البريطانية في مصر",["BUE"],["British University in Egypt"],[]),
"Egyptian University in Alamein":("الجامعة المصرية بالعلمين",[],[],[]),
"New Heliopolis University":("جامعة مصر الجديدة",[],[],[]),
"German International University in the Administrative Capital":("الجامعة الألمانية الدولية",["GIU"],["German International University"],[]),
"Egypt-Japan University of Science and Technology":("الجامعة المصرية اليابانية للعلوم والتكنولوجيا",["E-JUST","EJUST"],[],[]),
"Arab Academy for Science, Technology and Maritime Transport":("الأكاديمية العربية للعلوم والتكنولوجيا والنقل البحري",["AASTMT","AAST"],[],[]),
"Coventry University - Cairo Branch":(None,["COV","Coventry Egypt"],["Coventry University Egypt","Coventry University Cairo Branch"],[]),
"University of Prince Edward Island - Cairo Branch":(None,["UPEI Cairo","UPEI Egypt"],["University of Prince Edward Island Egypt Branch"],[]),
}
def slug(name): return re.sub(r"[^a-z0-9]+","-",name.lower()).strip("-")
items=[]
for category,names in groups.items():
 for name in names:
  ar,abbr,variations,arvars=meta.get(name,(None,[],[],[]))
  source=("https://scu.eg/branches-of-international-universities/" if name=="Anglia Ruskin University - Egypt Branch" else "https://scu.eg/accredited-private-universities/" if name in {"Egyptian University in Alamein","New Heliopolis University"} else SOURCE)
  item={"id":"eg-"+slug(name),"official_english_name":"Capital-Helwan University" if name=="Capital University" else name,"official_arabic_name":ar,"abbreviations":abbr,"english_variations":variations,"arabic_variations":arvars,"category":category,"diversity_category":"private" if name=="The American University in Cairo" else CATEGORY_GROUPS[category],"source_url":source,"last_verified_date":VERIFIED}
  if name=="The American University in Cairo":
   item["diversity_source_url"]="https://www1.aucegypt.edu/catalog06/catalog06.pdf"
   item["classification_note"]="Private institution established under an international cultural agreement; retain both classifications."
  items.append(item)
payload={"schema_version":1,"description":"Universities and university branches verified from official Egyptian higher-education listings; higher institutes are excluded.","sources":[SOURCE,"https://scu.eg/en/universities-and-institutions/"],"universities":items}
Path(__file__).with_name("university_directory.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(len(items))
