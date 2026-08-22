#!/usr/bin/env python3
"""Generate the example corpus used by the Shuddhi demo.

The generated shards contain DELIBERATELY PLANTED DEFECTS so every filter in
the pipeline has something to catch. The generated files are committed, so
you do not need to run this — it exists to document how the sample was made
and to let you regenerate it after edits.

Planted, per shard:
  sample_eng.txt   1 exact duplicate · 1 near-duplicate · 1 boilerplate/junk
                   doc · 1 PII doc · 1 "toxic" doc (demo lexicon) · 1 doc
                   contaminated with an eval-set item
  sample_hin.txt   1 near-duplicate
  customer_export.txt  registered as data_class "customer" -> always REFUSED
"""

import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "corpus")

# 24 topic-distinct English paragraphs. Deliberately varied vocabulary so
# ordinary documents do NOT look like near-duplicates of one another.
ARTICLES = [
    ("monsoon", "The monsoon arrived along the western coast nearly two weeks earlier than the historical average this year. Farmers in the coastal districts welcomed the early rainfall after an extended dry spell that had delayed sowing. Agricultural officers reported that reservoir levels were recovering steadily across the region. Market committees expect vegetable supply to normalise before the end of the month."),
    ("railways", "The railway board approved a revised timetable for freight corridors serving the northern industrial belt. Container traffic on the route has grown for six consecutive quarters, straining existing scheduling windows. Engineers will add three passing loops to reduce waiting time at busy junctions. Officials said the changes take effect at the start of the next financial quarter."),
    ("textiles", "Handloom weavers in the district cooperative reported a strong season for traditional cotton sarees. Demand from urban retailers rose after a design collaboration with a national fashion label. The cooperative has invested in natural dye processing to reduce effluent discharge. Younger weavers are being trained on both traditional patterns and inventory software."),
    ("solar", "A new rooftop solar installation programme opened applications for residential customers this week. Households can claim a subsidy on systems below five kilowatts through the state portal. Installers must be empanelled and provide a five year maintenance commitment. Officials estimate the scheme will add sixty megawatts of distributed capacity."),
    ("fisheries", "Fishing communities along the eastern coastline are adopting satellite based advisories for safer voyages. The advisories combine wind speed forecasts with shoal location estimates from ocean colour data. Cooperative societies distribute the alerts through a regional language mobile application. Early adopters report shorter trips and reduced fuel consumption."),
    ("education", "The district education office launched a remedial reading programme for primary school students. Teachers received a week of training in phonics based instruction and continuous assessment. Volunteers from local colleges assist with small group sessions three afternoons a week. Baseline testing will be repeated at the end of the academic term."),
    ("telemedicine", "A network of rural health centres began offering specialist consultations over video links. Nurses at the centre collect vital signs and upload them before the scheduled appointment. Cardiologists and dermatologists in the district hospital review cases twice weekly. The programme has reduced unnecessary travel for elderly patients considerably."),
    ("cricket", "The state cricket association announced an expanded under nineteen tournament for the coming season. Twelve district teams will compete in a longer format designed to develop patient batting. Selectors emphasised that fielding standards would weigh heavily in final selection. Matches will be played at four venues with improved practice facilities."),
    ("water", "Municipal engineers completed a survey of distribution losses across the older water network. Nearly a third of supplied volume was unaccounted for, largely through ageing joints. A phased replacement of cast iron mains will begin in the northern wards. Pressure monitoring devices are being installed to detect leaks earlier."),
    ("logistics", "Warehouse operators near the inland container depot are automating their inbound sorting lines. Barcode gantries now capture consignment details without manual scanning at the dock. The change reduced average unloading time for a full trailer by nearly half. Staff previously assigned to scanning have moved to quality inspection roles."),
    ("forestry", "A community forest management group reported successful natural regeneration on degraded slopes. Grazing was regulated through a rotational agreement negotiated among six villages. Native species now dominate the understorey where invasive shrubs had spread. Rainfall retention on the treated slopes improved measurably over three seasons."),
    ("dairy", "The dairy cooperative installed bulk milk chillers at eleven additional collection points. Chilling within two hours of milking has reduced spoilage during summer months. Member farmers receive payments based on fat content measured at collection. The cooperative plans a small cheese production unit next year."),
    ("crafts", "Artisans working in brass metalwork have formed a joint marketing collective. Individual workshops previously sold through intermediaries at thin margins. The collective operates a shared showroom and handles export documentation centrally. Design consultants advise on adapting traditional forms for contemporary interiors."),
    ("transport", "The city transport authority added forty electric buses to its suburban routes. Depot charging infrastructure was commissioned ahead of the vehicle delivery schedule. Drivers completed a training module on regenerative braking and range management. Early operating data shows lower energy cost per kilometre than diesel equivalents."),
    ("horticulture", "Orchard owners in the hill districts are trialling high density apple plantations. Dwarf rootstock allows earlier fruiting and simpler harvesting without ladders. Drip irrigation paired with soil moisture sensors reduced water use substantially. Extension officers are monitoring pest pressure under the denser canopy."),
    ("libraries", "A network of village reading rooms received a consignment of regional language books. Each reading room is managed by a volunteer committee with a small annual grant. Evening sessions for school children have become the most attended activity. Usage records will inform the next round of title selection."),
    ("weather", "Meteorologists installed additional automatic weather stations across the plateau region. The denser network improves short range forecasting for agricultural advisories. Data is transmitted hourly and published on a public dashboard. Researchers will use the archive to study changing pre monsoon patterns."),
    ("pharma", "A generic formulation plant received approval to supply an additional export market. Regulatory inspectors reviewed documentation practices and environmental controls. The facility has expanded its quality laboratory and hired analytical chemists. Production of the approved lines begins after validation batches are cleared."),
    ("tourism", "Heritage walk operators in the old quarter reported a strong post season demand. Guides trained in architectural history lead small groups through lesser known lanes. Residents were consulted on route timing to limit disturbance in narrow streets. Ticket revenue partly funds conservation of two stepwells nearby."),
    ("mining", "Environmental clearance conditions for the limestone quarry were revised after a review. Dust suppression must now operate continuously during crushing operations. Groundwater monitoring wells were added at the boundary of the lease area. The operator submitted a revised progressive restoration plan."),
    ("startups", "An incubator focused on agricultural technology selected eight teams for its new cohort. Selected teams work on soil testing, cold storage and market linkage problems. Mentors include agronomists as well as software engineers and finance specialists. The programme concludes with field pilots rather than a demonstration day."),
    ("sports", "The municipal swimming complex reopened after a nine month renovation programme. Filtration systems were replaced and the shallow pool was rebuilt for lessons. Coaching slots for school groups are allocated through an online booking system. Membership has already exceeded the level recorded before the closure."),
    ("power", "Grid operators completed a reliability upgrade on the substation serving the industrial estate. Redundant transformers reduce the risk of extended outages during peak demand. Protection relays were replaced with digital units allowing remote diagnostics. Planned maintenance can now be carried out without interrupting supply."),
    ("archives", "State archivists began digitising nineteenth century revenue records held in the district office. Fragile volumes are stabilised before scanning under controlled lighting. Metadata is captured in both the original script and a transliterated form. Researchers will access the collection through a searchable public catalogue."),
]

HINDI = [
    "जिला प्रशासन ने ग्रामीण क्षेत्रों में पेयजल आपूर्ति सुधारने के लिए नई योजना शुरू की है। पंचायत स्तर पर जल समितियाँ बनाई जाएँगी जो रखरखाव की जिम्मेदारी सँभालेंगी। अधिकारियों के अनुसार अगले वर्ष तक सभी गाँवों तक पाइपलाइन पहुँचा दी जाएगी। समिति ने कहा कि कार्य की प्रगति की समीक्षा हर तीन माह में की जाएगी और आवश्यक सुधार तुरंत लागू किए जाएँगे। स्थानीय निवासियों से सुझाव लेने के लिए खुली बैठकें भी आयोजित की जा रही हैं।",
    "राज्य सरकार ने किसानों के लिए बीज वितरण केंद्रों की संख्या बढ़ाने का निर्णय लिया है। नए केंद्र उन ब्लॉकों में खोले जाएँगे जहाँ अब तक किसानों को लंबी दूरी तय करनी पड़ती थी। कृषि विभाग ने गुणवत्ता जाँच की व्यवस्था भी मजबूत की है। विभाग ने बताया कि आवंटित बजट का उपयोग पारदर्शी ढंग से किया जाएगा और खर्च का ब्योरा सार्वजनिक किया जाएगा। योजना की सफलता के बाद इसे अन्य जिलों में भी लागू करने पर विचार होगा।",
    "शहर की नगरपालिका ने ठोस अपशिष्ट प्रबंधन के लिए विकेंद्रीकृत खाद इकाइयाँ स्थापित की हैं। प्रत्येक वार्ड में गीले कचरे से खाद बनाई जा रही है जिसे उद्यानों में उपयोग किया जाता है। निवासियों को घर पर ही कचरा अलग करने के लिए प्रशिक्षित किया गया। अधिकारियों ने स्पष्ट किया कि गुणवत्ता जाँच के लिए स्वतंत्र दल नियुक्त किया गया है। शिकायत निवारण के लिए एक हेल्पलाइन नंबर भी जारी किया गया है जिस पर कोई भी नागरिक संपर्क कर सकता है।",
    "पर्वतीय क्षेत्र में सेब उत्पादकों ने इस मौसम में बेहतर उपज दर्ज की है। मौसम अनुकूल रहने और समय पर सिंचाई उपलब्ध होने से फल का आकार सुधरा है। बागवानी विभाग ने भंडारण सुविधाओं के विस्तार की घोषणा की है। समिति ने कहा कि कार्य की प्रगति की समीक्षा हर तीन माह में की जाएगी और आवश्यक सुधार तुरंत लागू किए जाएँगे। स्थानीय निवासियों से सुझाव लेने के लिए खुली बैठकें भी आयोजित की जा रही हैं।",
    "पुस्तकालय विभाग ने विद्यालयों में पठन कक्षों की स्थापना का कार्यक्रम आरंभ किया है। प्रत्येक कक्ष में क्षेत्रीय भाषा की पुस्तकें और बाल साहित्य उपलब्ध कराया जाएगा। शिक्षकों को पठन गतिविधियाँ संचालित करने का प्रशिक्षण दिया जा रहा है। विभाग ने बताया कि आवंटित बजट का उपयोग पारदर्शी ढंग से किया जाएगा और खर्च का ब्योरा सार्वजनिक किया जाएगा। योजना की सफलता के बाद इसे अन्य जिलों में भी लागू करने पर विचार होगा।",
    "स्वास्थ्य केंद्रों पर टेलीमेडिसिन सेवा शुरू होने से मरीजों को विशेषज्ञ परामर्श मिलने लगा है। नर्सें जाँच के आँकड़े पहले ही अपलोड कर देती हैं जिससे परामर्श तेज होता है। बुजुर्ग मरीजों की यात्रा में उल्लेखनीय कमी आई है। अधिकारियों ने स्पष्ट किया कि गुणवत्ता जाँच के लिए स्वतंत्र दल नियुक्त किया गया है। शिकायत निवारण के लिए एक हेल्पलाइन नंबर भी जारी किया गया है जिस पर कोई भी नागरिक संपर्क कर सकता है।",
    "मत्स्य पालन विभाग ने तालाब आधारित मछली उत्पादन के लिए प्रशिक्षण शिविर आयोजित किए। प्रतिभागियों को जल गुणवत्ता प्रबंधन और चारा प्रबंधन की जानकारी दी गई। सहकारी समितियों के माध्यम से विपणन व्यवस्था सुदृढ़ की जा रही है। समिति ने कहा कि कार्य की प्रगति की समीक्षा हर तीन माह में की जाएगी और आवश्यक सुधार तुरंत लागू किए जाएँगे। स्थानीय निवासियों से सुझाव लेने के लिए खुली बैठकें भी आयोजित की जा रही हैं।",
    "परिवहन निगम ने उपनगरीय मार्गों पर इलेक्ट्रिक बसें चलाना शुरू किया है। डिपो में चार्जिंग सुविधा वाहनों के आने से पहले ही तैयार कर ली गई थी। चालकों को ऊर्जा दक्ष संचालन का विशेष प्रशिक्षण दिया गया है। विभाग ने बताया कि आवंटित बजट का उपयोग पारदर्शी ढंग से किया जाएगा और खर्च का ब्योरा सार्वजनिक किया जाएगा। योजना की सफलता के बाद इसे अन्य जिलों में भी लागू करने पर विचार होगा।",
    "हथकरघा बुनकरों की सहकारी समिति ने इस वर्ष अच्छी बिक्री दर्ज की है। शहरी बाजारों से माँग बढ़ने के बाद उत्पादन क्षमता बढ़ाई गई। प्राकृतिक रंगों के उपयोग से पर्यावरणीय प्रभाव कम हुआ है। अधिकारियों ने स्पष्ट किया कि गुणवत्ता जाँच के लिए स्वतंत्र दल नियुक्त किया गया है। शिकायत निवारण के लिए एक हेल्पलाइन नंबर भी जारी किया गया है जिस पर कोई भी नागरिक संपर्क कर सकता है।",
    "वन प्रबंधन समिति ने ढलानों पर प्राकृतिक पुनर्जनन में सफलता प्राप्त की है। छह गाँवों के बीच चराई के लिए बारी-बारी व्यवस्था पर सहमति बनी। देशी प्रजातियाँ अब क्षेत्र में पुनः फैलने लगी हैं। समिति ने कहा कि कार्य की प्रगति की समीक्षा हर तीन माह में की जाएगी और आवश्यक सुधार तुरंत लागू किए जाएँगे। स्थानीय निवासियों से सुझाव लेने के लिए खुली बैठकें भी आयोजित की जा रही हैं।",
]


def build_english() -> list[str]:
    docs = [f"{body}" for _topic, body in ARTICLES]
    # --- planted defects ---
    docs.append(docs[0])                                   # exact duplicate
    docs.append(docs[1] + " A short editorial note was appended to this report after publication.")  # near-duplicate
    docs.append(("Buy cheap widgets online today. Click here. Subscribe to our newsletter.\n" * 25).strip())  # junk
    docs.append(
        "Please direct billing questions to accounts@example.com or call +91 9876543210 during "
        "working hours. The reference card number on file ends with 4111 1111 1111 1111 and the "
        "request originated from 192.168.10.24 according to the access log. Our records also list "
        "PAN ABCDE1234F for the registered entity, which should be corrected at the next review."
    )                                                       # PII
    docs.append(
        "This forum thread is a complete zorbleflax of nonsense and the moderator called it a "
        "flarbnok waste of everyone's time. Another user replied that the whole zorbleflax argument "
        "was a flarbnok distraction from the actual topic under discussion here today. The thread "
        "was eventually locked after repeated zorbleflax and flarbnok remarks from both sides."
    )                                                       # toxic (demo lexicon)
    docs.append(
        "Here is a practice exercise I found in a tutorial collection online. There is a bug in "
        "src/orders.js. findOrder crashes with a TypeError when the id is not present. Fix it. Do "
        "not change anything else. Several readers posted their solutions in the comments below and "
        "discussed which approach was the most readable for a beginner."
    )                                                       # contamination
    # A single high-entropy outlier for the perplexity proxy. Deterministic,
    # and deliberately NON-repeating: two similar junk documents would be
    # caught by the near-dup filter first, and repeated text would teach the
    # per-shard language model its own pattern (the model is trained on this
    # very shard), which is exactly how an outlier stops looking like one.
    import random
    rng = random.Random(20260813)
    cons, vows = "bcdfghjklmnpqrstvwxz", "aeiou"
    blob = " ".join(
        "".join(rng.choice(cons if i % 3 else vows) for i in range(rng.randint(3, 9)))
        for _ in range(260)
    )
    docs.append(blob)                                       # perplexity outlier
    return docs


def build_hindi() -> list[str]:
    docs = list(HINDI)
    docs.append(docs[2] + " यह टिप्पणी प्रकाशन के बाद जोड़ी गई थी।")   # near-duplicate
    return docs


CUSTOMER = [
    "Ticket 88213: customer reports intermittent login failures on the mobile application.",
    "Ticket 88214: billing discrepancy raised for invoice number 5521 issued last quarter.",
    "Ticket 88215: request to export account data before the scheduled plan migration.",
]


def write(name: str, docs: list[str]) -> None:
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(d.strip() for d in docs) + "\n\n")
    print(f"{name}: {len(docs)} documents, {os.path.getsize(path)} bytes")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    write("sample_eng.txt", build_english())
    write("sample_hin.txt", build_hindi())
    write("customer_export.txt", CUSTOMER)
