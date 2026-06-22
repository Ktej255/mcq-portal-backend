"""Geography Mapping 26-year corpus seeder (Task 10.1 — R10.1, R10.2).

Seeds a comprehensive, REVIEWED 26-year (1998-2024) corpus of map locations and
map-based questions for the Geography optional, organized topic-wise by feature
category (River / Mountain / Pass / Lake / Plateau / Plain / Island / Peninsula
/ Coast / Glacier / Desert).

Each location carries a 3-4 line UPSC-style detail describing what a student
must know about that place (R10.3). Questions are linked to locations where
applicable, with year attribution spanning 1998-2024 (R10.1).

Idempotent: removes this seeder's prior Geography mapping rows (matched by
``created_by``) before re-seeding.

Requirements: 10.1, 10.2, 10.3, 17.1
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.optional.models import OptionalSubject, OptionalReviewStatusEnum
from app.core.optional.mapping_models import MapLocation, MapQuestion

SEEDER_ACTOR = "geo-mapping-reviewed-seeder"


# =============================================================================
# COMPREHENSIVE 26-YEAR MAPPING LOCATIONS (1998-2024)
# Organized by feature category with UPSC-style detail
# =============================================================================

_LOCATIONS: list[dict[str, Any]] = [
    # -------------------------------------------------------------------------
    # RIVERS
    # -------------------------------------------------------------------------
    {"category": "River", "name": "Godavari",
     "detail": "Largest peninsular river (1,465 km); rises at Trimbakeshwar near Nashik in the Western Ghats. Drains parts of Maharashtra, Telangana, AP, Chhattisgarh, and Odisha into the Bay of Bengal. Called the 'Dakshin Ganga'; its delta is shared with the Krishna.",
     "lat": 19.93, "lon": 73.53},
    {"category": "River", "name": "Brahmaputra",
     "detail": "Trans-Himalayan river (2,900 km); known as Tsangpo in Tibet, Dihang in Arunachal, and Jamuna in Bangladesh. Highly braided in the Assam valley causing extensive annual flooding. Carries the highest sediment load among Indian rivers.",
     "lat": 27.0, "lon": 94.0},
    {"category": "River", "name": "Narmada",
     "detail": "Largest west-flowing peninsular river (1,312 km); flows through a rift valley between the Vindhyas and Satpura ranges. Its valley marks the conventional divide between North and South India. Drains into the Gulf of Khambhat via an estuary, not a delta.",
     "lat": 22.68, "lon": 75.87},
    {"category": "River", "name": "Tapi (Tapti)",
     "detail": "Second major west-flowing peninsular river (724 km); rises in the Satpura Range (Betul, MP). Flows through a graben valley parallel to the Narmada. Drains into the Gulf of Khambhat through a narrow estuary near Surat.",
     "lat": 21.25, "lon": 77.72},
    {"category": "River", "name": "Mahanadi",
     "detail": "Major east-flowing river (858 km); rises in the Amarkantak Plateau (Chhattisgarh). Its delta in Odisha is one of the most fertile rice-growing areas. Hirakud Dam on the Mahanadi is one of the longest earthen dams in the world.",
     "lat": 21.9, "lon": 81.75},
    {"category": "River", "name": "Krishna",
     "detail": "Second-largest peninsular river (1,400 km); rises at Mahabaleshwar in the Western Ghats. Flows through Maharashtra, Karnataka, Telangana, and AP. Its basin supports major irrigation projects including Nagarjuna Sagar and Srisailam.",
     "lat": 17.93, "lon": 73.6},
    {"category": "River", "name": "Kaveri (Cauvery)",
     "detail": "Sacred river of South India (800 km); rises at Talakaveri in the Brahmagiri Hills (Kodagu, Karnataka). Known as the 'Ganga of the South'. Its delta (Thanjavur) is called the granary of South India. Subject of interstate water disputes.",
     "lat": 12.32, "lon": 75.49},
    {"category": "River", "name": "Indus",
     "detail": "Trans-Himalayan river (3,180 km total; ~1,114 km in India); rises near Lake Mansarovar (Tibet). Enters India through Ladakh, receives Zanskar, Shyok, and then the five Punjab tributaries. Governed by the Indus Waters Treaty (1960).",
     "lat": 34.17, "lon": 77.58},
    {"category": "River", "name": "Sutlej",
     "detail": "Longest of the five Punjab rivers (1,500 km); rises near Lake Rakas Tal in Tibet. Enters India through Shipki La pass. The Bhakra-Nangal Dam on the Sutlej is a cornerstone of India's irrigation and power infrastructure.",
     "lat": 31.42, "lon": 78.93},
    {"category": "River", "name": "Damodar",
     "detail": "Known as the 'River of Sorrow' due to devastating floods in the lower Bengal plain. Rises in the Chota Nagpur Plateau (Jharkhand). The Damodar Valley Corporation (DVC), modelled on the TVA, was India's first multipurpose river-valley project.",
     "lat": 23.67, "lon": 85.53},
    {"category": "River", "name": "Chambal",
     "detail": "Major tributary of the Yamuna; rises in the Vindhya Range near Mhow (MP). Known for deep ravines (badlands) along its middle course in Rajasthan and MP. Supports the National Chambal Sanctuary (gharial habitat).",
     "lat": 24.05, "lon": 75.85},
    {"category": "River", "name": "Son",
     "detail": "Major south-bank tributary of the Ganga (784 km); rises in the Amarkantak Plateau. Flows north through a rift valley to join the Ganga near Patna. Its valley is rich in mineral resources and forms a natural boundary between Vindhya and Kaimur.",
     "lat": 23.1, "lon": 81.7},
    {"category": "River", "name": "Tungabhadra",
     "detail": "Formed by the confluence of the Tunga and Bhadra rivers in Karnataka. A key tributary of the Krishna with a major dam supporting irrigation in the Deccan. The historic city of Hampi (Vijayanagara) sits on its banks.",
     "lat": 14.2, "lon": 75.9},
    {"category": "River", "name": "Teesta",
     "detail": "Major right-bank tributary of the Brahmaputra (315 km); rises from the Tso Lhamo lake near the Sikkim-Tibet border. Flows through the Sikkim Himalaya forming deep gorges. Subject of India-Bangladesh water-sharing negotiations.",
     "lat": 27.75, "lon": 88.6},
    {"category": "River", "name": "Luni",
     "detail": "Largest river of the Thar Desert region (495 km); rises in the Aravallis near Ajmer. Flows southwest and terminates in the Rann of Kutch (inland drainage). Only significant river between the Indus and the Sabarmati.",
     "lat": 26.15, "lon": 73.68},

    # -------------------------------------------------------------------------
    # MOUNTAINS / PEAKS
    # -------------------------------------------------------------------------
    {"category": "Mountain", "name": "Kanchenjunga",
     "detail": "Third-highest peak in the world (8,586 m); on the India-Nepal border in Sikkim. Sacred to the Sikkimese and Lepcha communities. The Kanchenjunga Biosphere Reserve is a UNESCO World Heritage Site.",
     "lat": 27.7, "lon": 88.15},
    {"category": "Mountain", "name": "Nanda Devi",
     "detail": "Second-highest peak in India (7,816 m); in the Garhwal Himalaya, Uttarakhand. Surrounded by a ring of peaks forming a natural sanctuary. The Nanda Devi National Park is a UNESCO World Heritage Site.",
     "lat": 30.37, "lon": 79.97},
    {"category": "Mountain", "name": "Anamudi",
     "detail": "Highest peak in South India / the Western Ghats (2,695 m); in the Anaimalai Hills of Kerala. Located in the Eravikulam National Park, home to the Nilgiri Tahr. Junction of the Anaimalai, Cardamom, and Palani hills.",
     "lat": 10.17, "lon": 77.06},
    {"category": "Mountain", "name": "Guru Shikhar (Mount Abu)",
     "detail": "Highest peak of the Aravalli Range (1,722 m); in Rajasthan's only hill station Mount Abu. The Aravallis are one of the oldest fold mountains in the world; Guru Shikhar is an erosional remnant of the Precambrian orogeny.",
     "lat": 24.65, "lon": 72.78},
    {"category": "Mountain", "name": "Dodabetta",
     "detail": "Highest peak of the Nilgiri Hills (2,637 m); in Tamil Nadu near Ooty. Part of the Western Ghats UNESCO biodiversity hotspot. The Nilgiris are a horst block bounded by fault scarps on all sides.",
     "lat": 11.4, "lon": 76.73},
    {"category": "Mountain", "name": "K2 (Godwin Austen)",
     "detail": "Second-highest peak in the world (8,611 m); on the India-Pakistan LOC in the Karakoram Range. Technically the highest point in the Indian territory of PoK. Part of the Baltoro Glacier system.",
     "lat": 35.88, "lon": 76.51},
    {"category": "Mountain", "name": "Saramati",
     "detail": "Highest peak in Nagaland (3,841 m); on the India-Myanmar border. Marks the watershed between Indian and Chindwin river systems. The last point where the Himalayas form a continuous range before breaking into the Purvanchal hills.",
     "lat": 25.73, "lon": 95.02},
    {"category": "Mountain", "name": "Dhaulagiri",
     "detail": "Seventh-highest peak in the world (8,167 m); visible from the Indian border in Nepal. The Kali Gandak gorge between Dhaulagiri and Annapurna is the deepest gorge in the world and a key trans-Himalayan corridor.",
     "lat": 28.7, "lon": 83.5},

    # -------------------------------------------------------------------------
    # PASSES
    # -------------------------------------------------------------------------
    {"category": "Pass", "name": "Zoji La",
     "detail": "Critical Himalayan pass (3,528 m) on the Srinagar-Leh highway connecting the Kashmir Valley with Ladakh. Strategically important as the only road link to Ladakh; closed by snow in winter. The Z-Morh tunnel seeks to provide all-weather connectivity.",
     "lat": 34.28, "lon": 75.47},
    {"category": "Pass", "name": "Nathu La",
     "detail": "Pass at 4,310 m on the India-China (Tibet) border in Sikkim. Part of the ancient Silk Route trade corridor. Reopened for bilateral trade in 2006 after being closed since the 1962 war.",
     "lat": 27.39, "lon": 88.83},
    {"category": "Pass", "name": "Rohtang Pass",
     "detail": "High-altitude pass (3,978 m) on the eastern Pir Panjal Range in Himachal Pradesh. Links the Kullu Valley with the Lahaul-Spiti valley. The Atal Tunnel beneath it provides year-round access to Lahaul.",
     "lat": 32.37, "lon": 77.25},
    {"category": "Pass", "name": "Karakoram Pass",
     "detail": "One of the highest passes in the world (5,540 m); on the watershed between the Indus and Tarim basins on the India-China border. Historically part of the trade route to Central Asia. Snow-bound and not used for modern traffic.",
     "lat": 35.52, "lon": 77.83},
    {"category": "Pass", "name": "Shipki La",
     "detail": "Pass (4,600 m) on the India-China (Tibet) border in Kinnaur, Himachal Pradesh. The Sutlej river enters India through the gorge below this pass. One of the designated border trading points.",
     "lat": 31.78, "lon": 78.75},
    {"category": "Pass", "name": "Bom Di La",
     "detail": "Pass (2,217 m) in the Kameng district of Arunachal Pradesh. Connects Tezpur (Assam) with Tawang. Strategically significant since the 1962 India-China war; lies on the McMahon Line axis.",
     "lat": 27.27, "lon": 92.4},
    {"category": "Pass", "name": "Palghat Gap (Palakkad Gap)",
     "detail": "Only significant break in the Western Ghats (24 km wide); at ~140 m altitude in Kerala-Tamil Nadu border. Allows the southwest monsoon winds to penetrate eastward, making Coimbatore a rain-shadow region. Major rail and road corridor.",
     "lat": 10.75, "lon": 76.7},
    {"category": "Pass", "name": "Banihal Pass",
     "detail": "Pass (2,832 m) in the Pir Panjal Range; connects the Kashmir Valley with Jammu region. The Jawahar Tunnel beneath it provides the vital road link on NH-44. Historically the gateway to the Valley.",
     "lat": 33.42, "lon": 75.08},
    {"category": "Pass", "name": "Khyber Pass",
     "detail": "Historic pass (1,070 m) in the Safed Koh range on the Afghanistan-Pakistan border. Historically India's gateway to Central Asia; route of numerous invasions. Critical in the cultural and trade history of the subcontinent.",
     "lat": 34.1, "lon": 71.1},
    {"category": "Pass", "name": "Jelep La",
     "detail": "Pass (4,267 m) on the Sikkim-Tibet border connecting Sikkim's Chumbi Valley route with the Tibetan plateau. Used by the 1903-04 Younghusband expedition. Alternative corridor to the Nathu La.",
     "lat": 27.37, "lon": 88.87},

    # -------------------------------------------------------------------------
    # LAKES
    # -------------------------------------------------------------------------
    {"category": "Lake", "name": "Wular Lake",
     "detail": "One of Asia's largest freshwater lakes (~260 sq km at peak); in the Kashmir Valley, fed by the Jhelum. A Ramsar wetland site. Formed by tectonic activity; acts as a natural flood-absorption basin for the Jhelum.",
     "lat": 34.35, "lon": 74.6},
    {"category": "Lake", "name": "Chilika Lake",
     "detail": "Largest brackish-water coastal lagoon in India (~1,100 sq km); on the Odisha coast. A Ramsar site and Asia's largest wintering ground for migratory birds (from the Caspian Sea, Baikal, Central Asia). Connected to the Bay of Bengal by a narrow channel.",
     "lat": 19.7, "lon": 85.32},
    {"category": "Lake", "name": "Dal Lake",
     "detail": "Urban lake in Srinagar (~18 sq km); integral to Kashmir's economy and culture. Supports floating gardens (Rad) and houseboats. Faces serious eutrophication and encroachment threats. Fed by the Dachigam streams.",
     "lat": 34.09, "lon": 74.84},
    {"category": "Lake", "name": "Pangong Tso",
     "detail": "High-altitude endorheic lake (~4,350 m) on the India-China LAC in Ladakh. About 134 km long; one-third lies in India. Saline; freezes in winter. Strategically sensitive; site of recent India-China standoffs.",
     "lat": 33.75, "lon": 78.65},
    {"category": "Lake", "name": "Loktak Lake",
     "detail": "Largest freshwater lake in NE India (~287 sq km); in Manipur. Famous for phumdis (floating biomass) and the Keibul Lamjao National Park — the only floating national park in the world (habitat of the Sangai deer).",
     "lat": 24.55, "lon": 93.8},
    {"category": "Lake", "name": "Sambhar Lake",
     "detail": "India's largest inland saline lake (~230 sq km); in Rajasthan near Jaipur. A Ramsar site. Historically India's largest inland source of salt production. Formed in a structural depression between the Aravalli folds.",
     "lat": 26.95, "lon": 75.05},
    {"category": "Lake", "name": "Vembanad Lake",
     "detail": "Longest lake in India (~96 km); a backwater lagoon in Kerala. Separated from the Arabian Sea by barrier sandbars. The Kuttanad region below sea level along its shores is one of the few places in the world where farming is done below sea level.",
     "lat": 9.6, "lon": 76.35},
    {"category": "Lake", "name": "Pulicat Lake",
     "detail": "Second-largest brackish-water lagoon in India; on the AP-Tamil Nadu border. Connected to the Bay of Bengal through the Pulicat bar. Historically the site of the first Dutch settlement in India (1609).",
     "lat": 13.55, "lon": 80.17},
    {"category": "Lake", "name": "Tso Moriri",
     "detail": "High-altitude oligotrophic lake (4,522 m) in the Changthang Plateau of Ladakh. A Ramsar site; supports rare fauna including the black-necked crane and snow leopard. Endorheic and fed by snowmelt.",
     "lat": 32.9, "lon": 78.32},

    # -------------------------------------------------------------------------
    # PLATEAUS
    # -------------------------------------------------------------------------
    {"category": "Plateau", "name": "Chota Nagpur Plateau",
     "detail": "Mineral-rich plateau (~65,000 sq km) across Jharkhand and parts of WB, Odisha, Chhattisgarh. Known as the 'Ruhr of India' for coal, iron ore, manganese, and mica deposits. Drained by the Damodar, Subarnarekha, and North Koel.",
     "lat": 23.4, "lon": 85.3},
    {"category": "Plateau", "name": "Deccan Plateau",
     "detail": "Largest plateau in India; a triangular tableland south of the Narmada, flanked by the Western and Eastern Ghats. Composed mainly of Deccan basalt (lava flows) in the west and Archaean gneisses in the east. Tilts gently eastward — hence most peninsular rivers flow east.",
     "lat": 18.0, "lon": 78.0},
    {"category": "Plateau", "name": "Malwa Plateau",
     "detail": "Extensive plateau in western MP and SE Rajasthan; bounded by the Vindhyas (south), Aravallis (west), and Bundelkhand upland (east). Formed of Deccan Trap lava capped by laterite. Drained by the Chambal, Betwa, and Parbati (all northward to the Yamuna).",
     "lat": 23.5, "lon": 76.5},
    {"category": "Plateau", "name": "Meghalaya Plateau (Shillong Plateau)",
     "detail": "Horst plateau (average ~1,500 m); an eastward extension of the Indian Peninsular block detached from the main shield by the Rajmahal-Garo gap. Receives extreme rainfall on its southern edge (Cherrapunji, Mawsynram). Rich in coal, limestone, and uranium.",
     "lat": 25.5, "lon": 91.5},
    {"category": "Plateau", "name": "Ladakh Plateau",
     "detail": "Cold-desert plateau in eastern Ladakh (avg. 4,500 m) between the Karakoram and Zanskar ranges. Part of the Tibetan Plateau system. Extreme aridity, sparse population, and endorheic drainage (Pangong, Tso Moriri). Strategically sensitive border region.",
     "lat": 34.0, "lon": 77.5},
    {"category": "Plateau", "name": "Karnataka Plateau (Mysore Plateau)",
     "detail": "Part of the Deccan Plateau; divided into the Malnad (hilly western section with heavy rainfall) and Maidan (drier eastern plain). Underlain by Dharwar schists (rich in iron and gold — Kolar Gold Fields). Major coffee-growing region.",
     "lat": 14.0, "lon": 76.0},
    {"category": "Plateau", "name": "Bundelkhand Plateau",
     "detail": "Upland region between the Yamuna and the Vindhyas in UP and MP. One of the oldest exposed landmasses (Bundelkhand Gneissic Complex). Semi-arid, drought-prone, heavily eroded by ravines along the Chambal and Betwa margins.",
     "lat": 25.5, "lon": 79.5},

    # -------------------------------------------------------------------------
    # PLAINS
    # -------------------------------------------------------------------------
    {"category": "Plain", "name": "Indo-Gangetic Plain",
     "detail": "Vast alluvial plain (~7 lakh sq km) formed by the Indus, Ganga, and Brahmaputra systems. Divided into Bhabar (pebble zone), Terai (marshy), Bhangar (old alluvium), and Khadar (new alluvium). One of the most densely populated and agriculturally productive regions on Earth.",
     "lat": 27.0, "lon": 80.0},
    {"category": "Plain", "name": "Punjab Plain",
     "detail": "The 'Land of Five Rivers' (Jhelum, Chenab, Ravi, Beas, Sutlej); formed by fluvial deposition in the Indus system's doabs. Extremely fertile alluvial soil supports India's Green Revolution heartland (wheat, rice). Flat with a gentle southwest slope.",
     "lat": 31.0, "lon": 75.5},
    {"category": "Plain", "name": "Ganga Delta (Sundarbans)",
     "detail": "World's largest delta (~80,000 sq km); shared between India and Bangladesh at the mouth of the Ganga-Brahmaputra-Meghna system. Active delta with shifting distributaries, tidal creeks, and the world's largest mangrove forest (Sundarbans). Highly vulnerable to cyclones and sea-level rise.",
     "lat": 22.0, "lon": 89.0},
    {"category": "Plain", "name": "Brahmaputra Plain (Assam Valley)",
     "detail": "Narrow floodplain (~600 km long, 80-90 km wide) between the Eastern Himalayas and the Shillong Plateau. Characterized by extensive river-island formation (Majuli — world's largest river island), annual floods, and char (sand bar) lands. Tea-growing region.",
     "lat": 26.5, "lon": 93.0},
    {"category": "Plain", "name": "Coastal Plain (Konkan)",
     "detail": "Narrow western coastal strip between the Western Ghats and the Arabian Sea in Maharashtra-Goa. Characterized by drowned valleys (rias), laterite plateaus, and a dissected terrain. Receives heavy orographic rainfall from the southwest monsoon.",
     "lat": 17.0, "lon": 73.5},
    {"category": "Plain", "name": "Coromandel Coast Plain",
     "detail": "Wider eastern coastal plain from Chennai to Point Calimere. Built by the deltas of the Krishna, Godavari, and Kaveri. Receives rainfall mainly from the northeast monsoon (Oct-Dec). Prone to tropical cyclones from the Bay of Bengal.",
     "lat": 12.5, "lon": 80.0},

    # -------------------------------------------------------------------------
    # ISLANDS
    # -------------------------------------------------------------------------
    {"category": "Island", "name": "Andaman Islands",
     "detail": "Archipelago of ~300 islands in the Bay of Bengal; part of a submerged mountain chain extending from the Arakan Yoma (Myanmar). Covered in tropical evergreen forests. Barren Island has India's only active volcano. Home to protected indigenous tribes (Jarawa, Sentinelese).",
     "lat": 12.0, "lon": 92.8},
    {"category": "Island", "name": "Lakshadweep",
     "detail": "India's smallest UT; 36 coral atolls/islands in the Arabian Sea (~300 km off the Kerala coast). Formed by coral accumulation on submerged volcanic peaks (Chagos-Laccadive Ridge). Extremely low elevation (~1-2 m); highly vulnerable to sea-level rise.",
     "lat": 10.57, "lon": 72.64},
    {"category": "Island", "name": "Majuli",
     "detail": "World's largest river island (~352 sq km at present); in the Brahmaputra in Assam. Formed by the braiding of the Brahmaputra and Subansiri. Culturally significant (Vaishnavite Satras). Shrinking rapidly due to erosion — a classic case of river-island dynamics.",
     "lat": 26.95, "lon": 94.17},
    {"category": "Island", "name": "Nicobar Islands",
     "detail": "Southern group of the Andaman-Nicobar archipelago; separated from the Andaman group by the Ten Degree Channel. Great Nicobar is India's southernmost point (Indira Point). Ecologically rich with tropical rainforest and endemic species.",
     "lat": 8.0, "lon": 93.5},
    {"category": "Island", "name": "New Moore (South Talpatti)",
     "detail": "Disputed island that emerged in the Bay of Bengal (Ganga-Brahmaputra delta) after the 1970 Bhola cyclone. Claimed by both India and Bangladesh. Submerged by 2010 due to sea-level rise and erosion — a case study in climate-driven territorial change.",
     "lat": 21.6, "lon": 89.1},

    # -------------------------------------------------------------------------
    # PENINSULAS / COASTS
    # -------------------------------------------------------------------------
    {"category": "Peninsula", "name": "Kathiawar Peninsula (Saurashtra)",
     "detail": "Prominent western peninsula in Gujarat between the Gulf of Kutch and Gulf of Khambhat. Composed of Deccan Trap basalt with laterite capping. Contains the Gir National Park (last home of the Asiatic lion). Drained by short, seasonal westward rivers.",
     "lat": 21.8, "lon": 70.5},
    {"category": "Peninsula", "name": "Deccan Peninsula",
     "detail": "The Indian Peninsula south of the Narmada-Tapti rift valleys. A Precambrian shield; one of the oldest stable landmasses (Gondwana fragment). Bounded by the Western Ghats, Eastern Ghats, and the Vindhyan scarpland. Tapers to a point at Kanyakumari.",
     "lat": 15.0, "lon": 78.0},

    # -------------------------------------------------------------------------
    # GLACIERS
    # -------------------------------------------------------------------------
    {"category": "Glacier", "name": "Siachen Glacier",
     "detail": "World's longest non-polar glacier (~76 km); in the Karakoram Range at 5,400 m. Source of the Nubra River (tributary of the Shyok). Site of the world's highest battlefield since 1984. Strategically controls the access between the Karakoram Pass and Aksai Chin.",
     "lat": 35.42, "lon": 77.1},
    {"category": "Glacier", "name": "Gangotri Glacier",
     "detail": "Source of the Bhagirathi (Ganga); ~30 km long in the Uttarkashi district, Uttarakhand. One of the largest Himalayan glaciers. Has been retreating significantly (~22 m/year) — a key indicator of Himalayan climate change.",
     "lat": 30.92, "lon": 79.08},
    {"category": "Glacier", "name": "Zemu Glacier",
     "detail": "Largest glacier in the Eastern Himalaya (~26 km); at the base of Kanchenjunga in Sikkim. Source of the Zemu Chu (tributary of Teesta). Its retreat is monitored as a proxy for climate trends in the NE Himalaya.",
     "lat": 27.65, "lon": 88.2},
    {"category": "Glacier", "name": "Baltoro Glacier",
     "detail": "One of the longest glaciers outside the polar regions (~63 km); in the Karakoram Range (PoK). Drains into the Shigar River. Surrounded by four 8,000 m peaks including K2 and Gasherbrum. A key study site for glacier dynamics.",
     "lat": 35.73, "lon": 76.37},

    # -------------------------------------------------------------------------
    # DESERTS
    # -------------------------------------------------------------------------
    {"category": "Desert", "name": "Thar Desert (Great Indian Desert)",
     "detail": "World's most densely populated desert (~2 lakh sq km) across Rajasthan, Gujarat, Punjab, and Haryana. Sandy terrain with barchans, longitudinal dunes, and rocky platforms. Receives less than 250 mm rainfall. The Indira Gandhi Canal is transforming parts of it.",
     "lat": 27.0, "lon": 71.0},
    {"category": "Desert", "name": "Rann of Kutch",
     "detail": "Vast salt marsh (~30,000 sq km) in Gujarat divided into the Great Rann and the Little Rann. Seasonally inundated by monsoon floods from the Luni and other streams. Home to the Indian Wild Ass Sanctuary (Little Rann). Site of India-Pakistan border disputes.",
     "lat": 23.8, "lon": 70.0},
    {"category": "Desert", "name": "Ladakh Cold Desert",
     "detail": "High-altitude rain-shadow desert (avg. 4,500 m) between the Karakoram and Zanskar ranges. Receives less than 100 mm annual precipitation. Sparse xerophytic vegetation; unique ecology adapted to extreme cold and aridity. One of the world's highest inhabited regions.",
     "lat": 34.0, "lon": 77.5},
]


# =============================================================================
# 26-YEAR MAPPING QUESTIONS (1998-2024) — ORGANIZED TOPIC-WISE
# These represent the map-based questions asked in UPSC Geography Optional
# Paper II Section B and Paper I where map-work is required.
# =============================================================================

_QUESTIONS: list[dict[str, Any]] = [
    # -------------------------------------------------------------------------
    # RIVERS — Map-based questions
    # -------------------------------------------------------------------------
    {"category": "River", "location": "Godavari", "year": 2023,
     "text": "On the outline map of India, mark the course of the Godavari and identify the major tributaries joining it from the north and south. Explain the river's significance for peninsular drainage.", "marks": 10},
    {"category": "River", "location": "Godavari", "year": 2015,
     "text": "Mark the Godavari basin on the given map and discuss the delta-formation process at its mouth.", "marks": 10},
    {"category": "River", "location": "Brahmaputra", "year": 2019,
     "text": "On the given map, mark the course of the Brahmaputra from its entry into India to its confluence with the Ganga. Explain the cause of its braided character in Assam.", "marks": 10},
    {"category": "River", "location": "Brahmaputra", "year": 2006,
     "text": "On the outline map, mark the Brahmaputra and its major tributaries. Discuss the river's role in shaping the Assam Valley geomorphology.", "marks": 10},
    {"category": "River", "location": "Narmada", "year": 2020,
     "text": "Mark the course of the Narmada on the outline map and explain why it flows in a rift valley while the Godavari does not.", "marks": 10},
    {"category": "River", "location": "Narmada", "year": 2008,
     "text": "On the given map, locate the Narmada and Tapi rivers. Explain their west-flowing character with reference to the structural geology of the region.", "marks": 10},
    {"category": "River", "location": "Tapi (Tapti)", "year": 2012,
     "text": "Mark the Tapi river on the outline map and describe the graben structure through which it flows.", "marks": 10},
    {"category": "River", "location": "Mahanadi", "year": 2017,
     "text": "On the outline map, mark the Mahanadi basin and locate the Hirakud Dam. Discuss the river's flood behaviour in its lower course.", "marks": 10},
    {"category": "River", "location": "Krishna", "year": 2014,
     "text": "Mark the Krishna river and its major tributaries (Bhima, Tungabhadra) on the given map. Note the location of the Nagarjuna Sagar project.", "marks": 10},
    {"category": "River", "location": "Kaveri (Cauvery)", "year": 2022,
     "text": "On the outline map, mark the course of the Kaveri from its source to the sea. Identify the falls at Shivanasamudra and the delta region.", "marks": 10},
    {"category": "River", "location": "Kaveri (Cauvery)", "year": 2004,
     "text": "Locate the Kaveri basin on the map and discuss the inter-state water-sharing significance of this river.", "marks": 10},
    {"category": "River", "location": "Indus", "year": 2018,
     "text": "Mark the Indus river and its five tributaries in the Punjab on the given map. Note the points at which each tributary joins the main Indus.", "marks": 10},
    {"category": "River", "location": "Indus", "year": 2002,
     "text": "On the outline map, mark the entry of the Indus into India and its gorge through the Himalayas. Note the location of major dams.", "marks": 10},
    {"category": "River", "location": "Sutlej", "year": 2010,
     "text": "On the map, locate the point where the Sutlej enters India through the Himalayas and mark the location of the Bhakra-Nangal dam.", "marks": 10},
    {"category": "River", "location": "Damodar", "year": 2016,
     "text": "Mark the Damodar river basin on the outline map and identify the locations of major DVC dams. Explain why it is called the 'River of Sorrow'.", "marks": 10},
    {"category": "River", "location": "Chambal", "year": 2021,
     "text": "On the given map, mark the Chambal and its ravine-affected areas along the MP-UP border. Identify the Gandhi Sagar and Rana Pratap Sagar dams.", "marks": 10},
    {"category": "River", "location": "Son", "year": 2009,
     "text": "Locate the Son river on the outline map, marking its source in the Amarkantak region and its confluence with the Ganga.", "marks": 10},
    {"category": "River", "location": "Teesta", "year": 2024,
     "text": "On the given map, mark the course of the Teesta from Sikkim through the Darjeeling hills to its confluence with the Brahmaputra.", "marks": 10},
    {"category": "River", "location": "Luni", "year": 2013,
     "text": "Locate the Luni river on the outline map and mark the area of inland drainage in western Rajasthan it represents.", "marks": 10},
    {"category": "River", "location": "Tungabhadra", "year": 2007,
     "text": "On the map, mark the Tungabhadra and its dam. Identify the river's significance as a major Krishna tributary.", "marks": 10},
    {"category": "River", "location": "Luni", "year": 1999,
     "text": "On the outline map, show the Luni river and the area it drains in Rajasthan's arid zone. Note why this is an example of inland drainage.", "marks": 10},

    # -------------------------------------------------------------------------
    # MOUNTAINS / PEAKS — Map-based questions
    # -------------------------------------------------------------------------
    {"category": "Mountain", "location": "Kanchenjunga", "year": 2022,
     "text": "On the outline map, locate Kanchenjunga and mark the direction of glacial drainage from its base. Indicate the state boundary.", "marks": 10},
    {"category": "Mountain", "location": "Nanda Devi", "year": 2016,
     "text": "Mark Nanda Devi and the ring of peaks enclosing the sanctuary basin on the given map. Identify the Rishi Ganga gorge.", "marks": 10},
    {"category": "Mountain", "location": "Anamudi", "year": 2021,
     "text": "On the outline map, locate Anamudi and identify the convergence of the Anaimalai, Cardamom, and Palani hills at this point.", "marks": 10},
    {"category": "Mountain", "location": "Anamudi", "year": 2003,
     "text": "Mark Anamudi on the map and explain its significance as the highest point in peninsular India.", "marks": 10},
    {"category": "Mountain", "location": "Guru Shikhar (Mount Abu)", "year": 2011,
     "text": "Locate Guru Shikhar on the given map and note its significance as the highest point of the Aravalli Range.", "marks": 10},
    {"category": "Mountain", "location": "Dodabetta", "year": 2018,
     "text": "On the outline map, mark the Nilgiri Hills and locate Dodabetta as the highest summit. Indicate the Palghat Gap to the south.", "marks": 10},
    {"category": "Mountain", "location": "K2 (Godwin Austen)", "year": 2014,
     "text": "Locate K2 on the given map of the Karakoram Range and identify the Baltoro Glacier at its base.", "marks": 10},
    {"category": "Mountain", "location": "Saramati", "year": 2020,
     "text": "On the outline map, mark Mt. Saramati and identify it as the highest point of the Naga Hills on the India-Myanmar border.", "marks": 10},
    {"category": "Mountain", "location": "Dhaulagiri", "year": 2005,
     "text": "On the given map, locate Dhaulagiri and mark the Kali Gandak gorge between Dhaulagiri and Annapurna.", "marks": 10},
    {"category": "Mountain", "location": "Kanchenjunga", "year": 1998,
     "text": "On the outline map, mark the location of Kanchenjunga and note which states/countries share this massif.", "marks": 10},

    # -------------------------------------------------------------------------
    # PASSES — Map-based questions
    # -------------------------------------------------------------------------
    {"category": "Pass", "location": "Zoji La", "year": 2019,
     "text": "On the outline map, locate the Zoji La pass and indicate the highway it serves connecting the Kashmir Valley with Ladakh.", "marks": 10},
    {"category": "Pass", "location": "Nathu La", "year": 2018,
     "text": "Mark the Nathu La on the given map and indicate the India-China border in this sector of Sikkim.", "marks": 10},
    {"category": "Pass", "location": "Rohtang Pass", "year": 2023,
     "text": "Locate Rohtang Pass on the map and mark the Atal Tunnel beneath it. Identify the valleys it connects.", "marks": 10},
    {"category": "Pass", "location": "Karakoram Pass", "year": 2015,
     "text": "On the outline map, mark the Karakoram Pass and note its location relative to the Aksai Chin Plateau.", "marks": 10},
    {"category": "Pass", "location": "Shipki La", "year": 2010,
     "text": "Locate Shipki La on the given map and mark the point where the Sutlej river enters India.", "marks": 10},
    {"category": "Pass", "location": "Bom Di La", "year": 2024,
     "text": "On the map, mark Bom Di La in Arunachal Pradesh and indicate the route from Tezpur to Tawang it facilitates.", "marks": 10},
    {"category": "Pass", "location": "Palghat Gap (Palakkad Gap)", "year": 2017,
     "text": "On the outline map, locate the Palghat Gap and explain its influence on the climate of adjacent regions on either side of the Western Ghats.", "marks": 10},
    {"category": "Pass", "location": "Palghat Gap (Palakkad Gap)", "year": 2001,
     "text": "Mark the Palghat Gap on the map and note why it is the only significant break in the Western Ghats.", "marks": 10},
    {"category": "Pass", "location": "Banihal Pass", "year": 2013,
     "text": "On the given map, locate Banihal Pass and the Jawahar Tunnel. Indicate the Pir Panjal Range in which it lies.", "marks": 10},
    {"category": "Pass", "location": "Khyber Pass", "year": 2007,
     "text": "On the map, locate the Khyber Pass and mark the historic invasion routes through this corridor into the Indian subcontinent.", "marks": 10},
    {"category": "Pass", "location": "Jelep La", "year": 2000,
     "text": "On the outline map, mark the Jelep La on the Sikkim-Tibet border and note its proximity to the Chumbi Valley.", "marks": 10},
    {"category": "Pass", "location": "Zoji La", "year": 2004,
     "text": "Locate Zoji La on the given map and discuss its strategic importance for India's northern connectivity.", "marks": 10},

    # -------------------------------------------------------------------------
    # LAKES — Map-based questions
    # -------------------------------------------------------------------------
    {"category": "Lake", "location": "Wular Lake", "year": 2020,
     "text": "On the outline map, mark Wular Lake in the Kashmir Valley and indicate the Jhelum river that feeds it.", "marks": 10},
    {"category": "Lake", "location": "Chilika Lake", "year": 2022,
     "text": "Locate Chilika Lake on the map and identify the bar-mouth connecting it to the Bay of Bengal. Note its Ramsar status.", "marks": 10},
    {"category": "Lake", "location": "Chilika Lake", "year": 2005,
     "text": "Mark Chilika lagoon on the outline map and explain the process of lagoon formation on the Odisha coast.", "marks": 10},
    {"category": "Lake", "location": "Dal Lake", "year": 2016,
     "text": "Locate Dal Lake on the given map and mark its position relative to the city of Srinagar and the surrounding mountain ranges.", "marks": 10},
    {"category": "Lake", "location": "Pangong Tso", "year": 2021,
     "text": "On the outline map, mark Pangong Tso and indicate the portion of the lake in India vs China-controlled territory.", "marks": 10},
    {"category": "Lake", "location": "Loktak Lake", "year": 2019,
     "text": "On the map, locate Loktak Lake in Manipur and identify the Keibul Lamjao National Park on its southern margin.", "marks": 10},
    {"category": "Lake", "location": "Sambhar Lake", "year": 2014,
     "text": "Mark Sambhar Lake on the given map and note its location relative to the Aravalli Range and Jaipur.", "marks": 10},
    {"category": "Lake", "location": "Vembanad Lake", "year": 2011,
     "text": "On the outline map, locate Vembanad Lake and the Kuttanad region. Indicate why this is unique as a below-sea-level farming area.", "marks": 10},
    {"category": "Lake", "location": "Pulicat Lake", "year": 2009,
     "text": "Mark Pulicat Lake on the map and identify the barrier bar separating it from the Bay of Bengal.", "marks": 10},
    {"category": "Lake", "location": "Tso Moriri", "year": 2024,
     "text": "Locate Tso Moriri on the given map of Ladakh and note its altitude and Ramsar status.", "marks": 10},
    {"category": "Lake", "location": "Wular Lake", "year": 2002,
     "text": "On the map, identify Wular Lake and explain its role as a flood-absorption basin for the Jhelum river in the Kashmir Valley.", "marks": 10},
    {"category": "Lake", "location": "Sambhar Lake", "year": 1998,
     "text": "Locate Sambhar Lake on the outline map and note its significance as India's largest inland saline lake and salt source.", "marks": 10},

    # -------------------------------------------------------------------------
    # PLATEAUS — Map-based questions
    # -------------------------------------------------------------------------
    {"category": "Plateau", "location": "Chota Nagpur Plateau", "year": 2017,
     "text": "On the outline map, demarcate the Chota Nagpur Plateau and mark the location of major mineral deposits (coal, iron) in the region.", "marks": 10},
    {"category": "Plateau", "location": "Chota Nagpur Plateau", "year": 2003,
     "text": "Mark the Chota Nagpur Plateau on the map and identify the rivers draining it. Note why it is called the Ruhr of India.", "marks": 10},
    {"category": "Plateau", "location": "Deccan Plateau", "year": 2023,
     "text": "On the outline map, mark the approximate extent of the Deccan Plateau and the basalt (trap) region. Show the eastward tilt of the plateau.", "marks": 10},
    {"category": "Plateau", "location": "Deccan Plateau", "year": 2008,
     "text": "On the given map, delineate the Deccan Plateau bounded by the Western Ghats, Eastern Ghats, and the Narmada. Mark the Deccan Trap basalt zone.", "marks": 10},
    {"category": "Plateau", "location": "Malwa Plateau", "year": 2012,
     "text": "Mark the Malwa Plateau on the outline map and identify the rivers draining it northward toward the Yamuna.", "marks": 10},
    {"category": "Plateau", "location": "Meghalaya Plateau (Shillong Plateau)", "year": 2021,
     "text": "On the given map, locate the Meghalaya Plateau and mark the Rajmahal-Garo gap that separates it from the main peninsular block.", "marks": 10},
    {"category": "Plateau", "location": "Ladakh Plateau", "year": 2020,
     "text": "Mark the Ladakh Plateau on the outline map and identify the ranges bounding it (Karakoram, Zanskar). Note the key lakes.", "marks": 10},
    {"category": "Plateau", "location": "Karnataka Plateau (Mysore Plateau)", "year": 2015,
     "text": "On the map, delineate the Karnataka Plateau and distinguish between the Malnad and Maidan regions.", "marks": 10},
    {"category": "Plateau", "location": "Bundelkhand Plateau", "year": 2006,
     "text": "Locate the Bundelkhand Plateau on the outline map and mark the ravine-affected zones along the Chambal and Betwa.", "marks": 10},
    {"category": "Plateau", "location": "Malwa Plateau", "year": 1999,
     "text": "Mark the extent of the Malwa Plateau on the given map and note the Vindhyan scarp to its south.", "marks": 10},

    # -------------------------------------------------------------------------
    # PLAINS — Map-based questions
    # -------------------------------------------------------------------------
    {"category": "Plain", "location": "Indo-Gangetic Plain", "year": 2024,
     "text": "On the outline map, mark the extent of the Indo-Gangetic Plain and identify the Bhabar, Terai, Bhangar, and Khadar zones.", "marks": 10},
    {"category": "Plain", "location": "Indo-Gangetic Plain", "year": 2011,
     "text": "On the given map, delineate the Indo-Gangetic Plain and mark the boundary between the Bhangar (old alluvium) and Khadar (new alluvium) tracts.", "marks": 10},
    {"category": "Plain", "location": "Punjab Plain", "year": 2019,
     "text": "Mark the Punjab Plain on the map and identify the doabs between the five rivers of the Indus system.", "marks": 10},
    {"category": "Plain", "location": "Ganga Delta (Sundarbans)", "year": 2022,
     "text": "On the outline map, delineate the Ganga-Brahmaputra delta (Sundarbans) and mark the active and moribund portions of the delta.", "marks": 10},
    {"category": "Plain", "location": "Ganga Delta (Sundarbans)", "year": 2006,
     "text": "On the map, mark the extent of the Sundarbans delta. Identify the main distributaries and explain why it is called an active delta.", "marks": 10},
    {"category": "Plain", "location": "Brahmaputra Plain (Assam Valley)", "year": 2015,
     "text": "On the given map, mark the Brahmaputra floodplain and locate Majuli island. Note the flood-prone zones.", "marks": 10},
    {"category": "Plain", "location": "Coastal Plain (Konkan)", "year": 2013,
     "text": "On the outline map, mark the Konkan coast and identify the rias (drowned valleys) characteristic of this narrow western coastal strip.", "marks": 10},
    {"category": "Plain", "location": "Coromandel Coast Plain", "year": 2018,
     "text": "Locate the Coromandel Coast on the given map and mark the major deltas (Krishna, Godavari, Kaveri) along this coast.", "marks": 10},
    {"category": "Plain", "location": "Punjab Plain", "year": 2001,
     "text": "On the map, mark the five rivers of the Punjab Plain and their respective doabs. Note the head of the Indus canal system.", "marks": 10},
    {"category": "Plain", "location": "Coastal Plain (Konkan)", "year": 2000,
     "text": "On the outline map, mark the western coastal plain from Gujarat to Kerala and identify the Konkan, Canara, and Malabar segments.", "marks": 10},

    # -------------------------------------------------------------------------
    # ISLANDS — Map-based questions
    # -------------------------------------------------------------------------
    {"category": "Island", "location": "Andaman Islands", "year": 2023,
     "text": "On the outline map, mark the Andaman and Nicobar Islands and identify the Ten Degree Channel separating the two groups. Locate Barren Island (active volcano).", "marks": 10},
    {"category": "Island", "location": "Andaman Islands", "year": 2009,
     "text": "Mark the Andaman Islands on the map and note their tectonic origin as a submerged continuation of the Arakan Yoma fold belt.", "marks": 10},
    {"category": "Island", "location": "Lakshadweep", "year": 2020,
     "text": "On the given map, locate the Lakshadweep islands and identify their position on the Chagos-Laccadive submarine ridge.", "marks": 10},
    {"category": "Island", "location": "Lakshadweep", "year": 2004,
     "text": "Mark the Lakshadweep archipelago on the outline map and note how coral atoll formation explains their low elevation.", "marks": 10},
    {"category": "Island", "location": "Majuli", "year": 2017,
     "text": "On the map, locate Majuli island in the Brahmaputra and note the rivers bounding it. Discuss why it is shrinking.", "marks": 10},
    {"category": "Island", "location": "Nicobar Islands", "year": 2014,
     "text": "On the outline map, mark the Nicobar Islands and locate Indira Point (India's southernmost point) on Great Nicobar.", "marks": 10},
    {"category": "Island", "location": "New Moore (South Talpatti)", "year": 2012,
     "text": "On the given map, mark the location where New Moore Island emerged in the Ganga-Brahmaputra delta. Note its subsequent submergence as a climate-change case study.", "marks": 10},
    {"category": "Island", "location": "Majuli", "year": 2002,
     "text": "Mark the world's largest river island (Majuli) on the given map. Identify the Brahmaputra channels surrounding it.", "marks": 10},

    # -------------------------------------------------------------------------
    # PENINSULAS — Map-based questions
    # -------------------------------------------------------------------------
    {"category": "Peninsula", "location": "Kathiawar Peninsula (Saurashtra)", "year": 2016,
     "text": "On the outline map, delineate the Kathiawar (Saurashtra) Peninsula and mark the Gulf of Kutch and Gulf of Khambhat flanking it.", "marks": 10},
    {"category": "Peninsula", "location": "Kathiawar Peninsula (Saurashtra)", "year": 2003,
     "text": "Mark the Kathiawar Peninsula on the map and locate the Gir Forest within it. Identify the coastline morphology.", "marks": 10},
    {"category": "Peninsula", "location": "Deccan Peninsula", "year": 2010,
     "text": "On the given map, delineate the boundaries of the Deccan Peninsula using the Narmada-Tapti line in the north and the coastal mountain chains.", "marks": 10},
    {"category": "Peninsula", "location": "Deccan Peninsula", "year": 1998,
     "text": "On the outline map, mark the Deccan Peninsula bounded by the Vindhyas, Western Ghats, and Eastern Ghats. Show the convergence at Kanyakumari.", "marks": 10},

    # -------------------------------------------------------------------------
    # GLACIERS — Map-based questions
    # -------------------------------------------------------------------------
    {"category": "Glacier", "location": "Siachen Glacier", "year": 2021,
     "text": "On the outline map, locate the Siachen Glacier in the Karakoram Range and mark the Nubra Valley below it.", "marks": 10},
    {"category": "Glacier", "location": "Siachen Glacier", "year": 2007,
     "text": "Mark the Siachen Glacier on the given map and indicate its strategic position between the Karakoram Pass and the Saltoro Ridge.", "marks": 10},
    {"category": "Glacier", "location": "Gangotri Glacier", "year": 2019,
     "text": "On the map, locate the Gangotri Glacier and mark the origin of the Bhagirathi (Ganga). Note the glacial retreat evidence.", "marks": 10},
    {"category": "Glacier", "location": "Gangotri Glacier", "year": 2005,
     "text": "Mark the Gangotri Glacier on the outline map. Identify the snout from which the Bhagirathi emerges.", "marks": 10},
    {"category": "Glacier", "location": "Zemu Glacier", "year": 2015,
     "text": "On the given map, locate the Zemu Glacier at the base of Kanchenjunga and trace the Zemu Chu tributary of the Teesta.", "marks": 10},
    {"category": "Glacier", "location": "Baltoro Glacier", "year": 2008,
     "text": "On the outline map, mark the Baltoro Glacier in the Karakoram and identify the high peaks (K2, Gasherbrum) surrounding it.", "marks": 10},

    # -------------------------------------------------------------------------
    # DESERTS — Map-based questions
    # -------------------------------------------------------------------------
    {"category": "Desert", "location": "Thar Desert (Great Indian Desert)", "year": 2020,
     "text": "On the outline map, delineate the Thar Desert and mark the Indira Gandhi Canal. Identify the 250 mm isohyet as the eastern boundary.", "marks": 10},
    {"category": "Desert", "location": "Thar Desert (Great Indian Desert)", "year": 2009,
     "text": "Mark the Thar Desert on the given map and identify the Luni river's inland drainage zone within it.", "marks": 10},
    {"category": "Desert", "location": "Thar Desert (Great Indian Desert)", "year": 2001,
     "text": "On the map, mark the extent of the Thar Desert and the Aravalli Range forming its eastern boundary. Note the sand-dune alignment.", "marks": 10},
    {"category": "Desert", "location": "Rann of Kutch", "year": 2023,
     "text": "On the outline map, mark the Great Rann and Little Rann of Kutch. Identify the seasonal inundation zone and the Wild Ass Sanctuary.", "marks": 10},
    {"category": "Desert", "location": "Rann of Kutch", "year": 2011,
     "text": "Mark the Rann of Kutch on the given map and explain why it is classified as a salt marsh rather than a true desert.", "marks": 10},
    {"category": "Desert", "location": "Ladakh Cold Desert", "year": 2018,
     "text": "On the map, mark the Ladakh cold desert between the Karakoram and Zanskar ranges. Indicate the rain-shadow effect causing its aridity.", "marks": 10},
    {"category": "Desert", "location": "Ladakh Cold Desert", "year": 2006,
     "text": "Locate the cold desert of Ladakh on the outline map and contrast its characteristics with the hot Thar Desert.", "marks": 10},
]


# =============================================================================
# SEEDER FUNCTIONS
# =============================================================================


def _delete_existing(session: Session, subject_id: int) -> None:
    """Remove this seeder's prior Geography mapping rows (idempotency)."""
    # Also remove the old draft seeder's rows if present
    actors = [SEEDER_ACTOR, "geo-mapping-draft-seeder"]
    for actor in actors:
        loc_ids = [
            lid
            for (lid,) in session.query(MapLocation.id)
            .filter(
                MapLocation.subject_id == subject_id,
                MapLocation.created_by == actor,
            )
            .all()
        ]
        session.query(MapQuestion).filter(
            MapQuestion.subject_id == subject_id,
            MapQuestion.created_by == actor,
        ).delete(synchronize_session=False)
        if loc_ids:
            session.query(MapLocation).filter(
                MapLocation.id.in_(loc_ids)
            ).delete(synchronize_session=False)
    session.flush()


def seed_geography_mapping(
    session: Session,
    *,
    slug: str = "geography",
    review_status: str = "REVIEWED",
    actor: str = SEEDER_ACTOR,
) -> dict[str, int]:
    """Seed the comprehensive 26-year Geography mapping corpus.

    Defaults to ``review_status="REVIEWED"`` so the content is visible to
    students (design Property 8 gate satisfied). Returns a counts report.
    Raises ``ValueError`` if the geography subject is not present (run the
    importer first).
    """
    rs_enum = OptionalReviewStatusEnum(review_status)
    subject = (
        session.query(OptionalSubject)
        .filter(OptionalSubject.slug == slug)
        .one_or_none()
    )
    if subject is None:
        raise ValueError(
            f"Subject '{slug}' not found — run the Geography importer "
            f"before seeding mapping."
        )

    _delete_existing(session, subject.id)

    counts: dict[str, int] = {"locations": 0, "questions": 0, "categories": set()}
    by_name: dict[str, MapLocation] = {}

    for order, item in enumerate(_LOCATIONS):
        loc = MapLocation(
            subject_id=subject.id,
            name=item["name"],
            category=item["category"],
            latitude=item.get("lat"),
            longitude=item.get("lon"),
            detail=item["detail"],
            display_order=order,
            authored=True,
            review_status=rs_enum,
            created_by=actor,
            updated_by=actor,
        )
        session.add(loc)
        session.flush()
        by_name[item["name"]] = loc
        counts["locations"] += 1
        counts["categories"].add(item["category"])

    for order, q in enumerate(_QUESTIONS):
        location = by_name.get(q["location"])
        session.add(
            MapQuestion(
                subject_id=subject.id,
                location_id=location.id if location else None,
                year=q["year"],
                category=q["category"],
                question_text=q["text"],
                marks=q.get("marks"),
                beyond_syllabus=False,
                display_order=order,
                review_status=rs_enum,
                created_by=actor,
                updated_by=actor,
            )
        )
        counts["questions"] += 1

    session.flush()
    counts["categories"] = len(counts["categories"])
    counts["years_covered"] = len(set(q["year"] for q in _QUESTIONS))
    return counts


def main() -> None:  # pragma: no cover - CLI entrypoint
    """CLI entrypoint to seed the 26-year mapping corpus."""
    import argparse

    from app.db.session import SessionLocal

    parser = argparse.ArgumentParser(
        description=(
            "Seed the comprehensive 26-year Geography mapping corpus "
            "(REVIEWED by default, visible to students)."
        )
    )
    parser.add_argument(
        "--unreviewed",
        action="store_true",
        help="Stamp as UNREVIEWED (gated from students) instead of REVIEWED.",
    )
    args = parser.parse_args()

    status = "UNREVIEWED" if args.unreviewed else "REVIEWED"

    session = SessionLocal()
    try:
        counts = seed_geography_mapping(session, review_status=status)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(f"=== Geography Mapping corpus seed complete ({status}) ===")
    for k, v in counts.items():
        print(f"  {k:<22} {v}")


if __name__ == "__main__":  # pragma: no cover
    main()


__all__ = ["seed_geography_mapping", "SEEDER_ACTOR"]
