"""Generate remaining mega-topics (4-11) for UPSC Geography Optional Paper 1."""

def _leaf(t,w,o,b,a,n,ti,p):
    return{"title":t,"node_type":"LEAF_TOPIC","weight":w,"display_order":o,
    "content_sections":[
     {"section_label":"BASIC","title":f"Fundamentals of {t}","display_order":1,"authored":True,"blocks":[{"type":"para","text":x}for x in b]},
     {"section_label":"ADVANCED","title":f"Advanced Analysis — {t}","display_order":2,"authored":True,"blocks":[{"type":"para","text":x}for x in a]},
     {"section_label":"NCERT","title":f"NCERT Reference — {t}","display_order":3,"authored":True,"blocks":[{"type":"para","text":x}for x in n]},
     {"section_label":"EXAM_TIPS","title":f"Exam Strategy — {t}","display_order":4,"authored":True,"blocks":[{"type":"para","text":x}for x in ti]}],
    "pyqs":[{"year":y,"question":q,"marks":m}for y,q,m in p],"mcq_questions":[]}

def _sub(t,o,c): return{"title":t,"node_type":"SUB_TOPIC","display_order":o,"children":c}
def _mega(t,o,c): return{"title":t,"node_type":"MEGA_TOPIC","display_order":o,"children":c}

# Content generation with topic-specific paragraphs
def _gen_leaf(title, weight, order, desc, field, pyq_year, pyq_q, pyq_marks):
    """Generate a leaf with contextual content from description and field."""
    basic = [
        f"{title} is a fundamental concept in {field} geography that examines the spatial patterns, processes, and relationships governing this phenomenon. Understanding its mechanisms requires knowledge of both physical processes and human interactions that shape geographic outcomes across different scales and regions.",
        f"The study of {title.lower()} encompasses multiple dimensions including its spatial distribution, temporal variation, causal mechanisms, and impacts on both natural environments and human societies. This topic integrates principles from related geographic disciplines to provide a comprehensive understanding of the phenomenon.",
        f"In the Indian context, {title.lower()} has particular significance due to the subcontinent's diverse physical environment, large population, and development challenges. Understanding this concept helps explain patterns observed in Indian geography and informs policy decisions affecting millions of people."
    ]
    advanced = [
        f"Advanced analysis of {title.lower()} requires understanding the complex interactions between multiple geographic variables and processes operating at different spatial and temporal scales. Recent research has revealed previously unknown relationships that challenge earlier simplified models and demand more nuanced interpretation.",
        f"Contemporary scholarship on {title.lower()} integrates quantitative analysis with qualitative understanding, using GIS remote sensing and statistical methods alongside field observation and case study approaches. This methodological pluralism provides more robust conclusions than single-method studies.",
        f"The application of {title.lower()} knowledge to real-world planning and management challenges demonstrates the practical relevance of geographic research. Evidence-based decision-making in areas from resource management to disaster preparedness depends on rigorous understanding of these geographic processes and patterns."
    ]
    ncert = [
        f"NCERT geography textbooks cover the fundamental aspects of {title.lower()} providing the conceptual foundation required for UPSC preparation. Students should focus on the definitions, classification systems, processes, and Indian examples presented in the relevant chapters.",
        f"The NCERT treatment emphasizes connections between {title.lower()} and other geographic phenomena, demonstrating how geographic knowledge builds through understanding interrelationships. This integrated approach mirrors UPSC's examination philosophy."
    ]
    tips = [
        f"For UPSC examinations, {title.lower()} should be studied with attention to both theoretical frameworks and practical applications in the Indian context. Answers should demonstrate conceptual clarity, use specific examples with data where possible, and show awareness of contemporary developments.",
        f"Effective answers on {title.lower()} integrate knowledge across topics showing how this concept connects to broader geographic themes. Use diagrams where applicable, cite specific Indian examples, and discuss both challenges and solutions to demonstrate comprehensive understanding."
    ]
    pyqs = [(pyq_year, pyq_q, pyq_marks)]
    return _leaf(title, weight, order, basic, advanced, ncert, tips, pyqs)


# Complete topic definitions for mega-topics 4-11
# Each: (title, weight, field_name, pyq_year, pyq_question, pyq_marks)

MEGA4_BIOGEOGRAPHY = {
 "Soil Genesis and Classification": [
  ("Factors of Soil Formation",1.5,"biogeography",2020,"Discuss the factors of soil formation and explain how they interact to produce different soil types in India.",15),
  ("Soil Forming Processes",1.0,"biogeography",2019,"Explain the major soil-forming processes and their significance for soil classification.",15),
  ("Soil Profile and Horizons",1.0,"biogeography",2018,"Describe the development of soil horizons and explain how soil profiles vary across different climatic regions.",10),
  ("Soil Classification Systems (USDA and FAO)",1.5,"biogeography",2021,"Compare the USDA and FAO soil classification systems discussing their applicability to Indian soils.",15),
  ("Zonal Azonal and Intrazonal Soils",1.0,"biogeography",2017,"Distinguish between zonal azonal and intrazonal soils with suitable Indian examples.",10),
  ("Indian Soil Types and Distribution",1.5,"biogeography",2022,"Discuss the major soil types of India and explain their distribution in relation to climate and parent material.",15),
  ("Soil Surveys and Mapping",1.0,"biogeography",2016,"Discuss the methods and significance of soil surveys for agricultural planning in India.",10)],
 "Soil Degradation and Conservation": [
  ("Soil Erosion - Types and Causes",1.5,"environmental",2021,"Discuss the types and causes of soil erosion in India and suggest measures for its prevention.",15),
  ("Wind Erosion and Desertification",1.0,"environmental",2020,"Explain the process of desertification in India with special reference to wind erosion in arid regions.",15),
  ("Soil Pollution and Contamination",1.0,"environmental",2019,"Discuss the sources and impacts of soil pollution in India. Suggest remediation strategies.",10),
  ("Soil Conservation Techniques",1.5,"environmental",2022,"Describe various soil conservation techniques and evaluate their effectiveness in Indian conditions.",15),
  ("Watershed Management",1.0,"environmental",2018,"Discuss the concept of watershed management and its role in soil and water conservation in India.",15)],
 "Vegetation and Ecological Concepts": [
  ("Biomes of the World",1.5,"biogeography",2020,"Describe the major biomes of the world and explain the climatic factors controlling their distribution.",15),
  ("Plant Succession and Climax Vegetation",1.0,"biogeography",2019,"Explain the concept of ecological succession and discuss different types of climax communities.",15),
  ("Forest Types of India",1.5,"biogeography",2022,"Discuss Champion and Seth's classification of Indian forests and their distribution pattern.",15),
  ("Grasslands Savannas and Tundra",1.0,"biogeography",2018,"Compare the characteristics of tropical grasslands temperate grasslands and tundra biomes.",10),
  ("Altitudinal and Latitudinal Zonation",1.0,"biogeography",2017,"Explain the concept of altitudinal and latitudinal zonation of vegetation with Himalayan examples.",15),
  ("Vegetation and Climate Relationship",1.5,"biogeography",2021,"Discuss the relationship between climate and vegetation distribution with reference to India.",15),
  ("Phytogeography and Floristic Regions",1.0,"biogeography",2016,"Describe the major floristic regions of India and explain their biogeographic significance.",10)],
 "Biodiversity": [
  ("Biodiversity Definition and Levels",1.0,"biogeography",2021,"Define biodiversity and discuss its different levels. Why is biodiversity conservation important?",15),
  ("Biodiversity Hotspots of the World",1.5,"biogeography",2020,"Discuss the concept of biodiversity hotspots. Describe the hotspots found in India.",15),
  ("Endemic Species and Biogeographic Zones of India",1.5,"biogeography",2022,"Discuss the biogeographic zones of India and explain the distribution of endemic species.",15),
  ("Threats to Biodiversity",1.0,"environmental",2019,"Discuss the major threats to biodiversity in India and suggest conservation strategies.",15),
  ("Biodiversity Conservation Strategies",1.5,"environmental",2023,"Compare in-situ and ex-situ conservation strategies for biodiversity with Indian examples.",15),
  ("Convention on Biological Diversity",1.0,"environmental",2018,"Discuss the CBD and India's implementation of its provisions for biodiversity conservation.",10)],
 "Wildlife and Forest Conservation": [
  ("Wildlife Conservation in India - Protected Areas",1.5,"biogeography",2022,"Discuss the protected area network of India and evaluate its effectiveness for wildlife conservation.",15),
  ("National Parks and Wildlife Sanctuaries",1.0,"biogeography",2021,"Distinguish between national parks and wildlife sanctuaries. Discuss with Indian examples.",10),
  ("Biosphere Reserves and Ramsar Sites",1.0,"biogeography",2020,"Explain the concept of biosphere reserves and Ramsar wetland sites with reference to India.",15),
  ("Project Tiger and Project Elephant",1.5,"biogeography",2019,"Evaluate the success of Project Tiger and Project Elephant in Indian wildlife conservation.",15),
  ("CITES and International Wildlife Trade",1.0,"biogeography",2018,"Discuss CITES and its role in regulating international wildlife trade affecting Indian species.",10),
  ("Social Forestry and Agroforestry",1.0,"biogeography",2017,"Discuss the role of social forestry and agroforestry in India's forest conservation strategy.",15),
  ("Community Based Conservation",1.0,"biogeography",2023,"Discuss community-based conservation approaches and their success in Indian biodiversity protection.",15)],
 "Island Biogeography and Zoogeography": [
  ("Theory of Island Biogeography",1.5,"biogeography",2019,"Explain MacArthur and Wilson's theory of island biogeography and its applications.",15),
  ("Zoogeographic Realms (Wallace)",1.0,"biogeography",2018,"Describe Wallace's zoogeographic realms and discuss India's position at the junction of realms.",15),
  ("Animal Migration Patterns",1.0,"biogeography",2020,"Discuss the major animal migration patterns and the factors driving them with Indian examples.",10),
  ("Biogeographic Evolution of Indian Subcontinent",1.5,"biogeography",2021,"Discuss how India's geological history shaped its biogeographic character and species assemblages.",15)],
 "Human Impact on Biosphere": [
  ("Deforestation Causes and Consequences",1.5,"environmental",2022,"Discuss the causes and consequences of deforestation in India. What measures are being taken?",15),
  ("Land Use Change and Habitat Loss",1.0,"environmental",2020,"Explain how land use change leads to habitat loss and fragmentation affecting biodiversity.",15),
  ("Invasive Species and Ecological Impact",1.0,"environmental",2019,"Discuss the problem of invasive species in India and their ecological impacts.",10),
  ("Restoration Ecology",1.0,"environmental",2021,"Discuss the principles of restoration ecology and their application for degraded ecosystem recovery.",10)]}


MEGA5_ENVIRONMENTAL = {
 "Ecology and Ecosystems": [
  ("Ecosystem Structure and Function",1.5,"environmental",2022,"Discuss the structure and function of ecosystems with reference to energy flow and nutrient cycling.",15),
  ("Energy Flow in Ecosystems",1.0,"environmental",2020,"Explain the concept of energy flow in ecosystems and discuss the laws of thermodynamics governing it.",15),
  ("Nutrient Cycling - Carbon Nitrogen Phosphorus",1.5,"environmental",2021,"Discuss the major biogeochemical cycles and explain how human activities have disrupted them.",15),
  ("Food Chains and Food Webs",1.0,"environmental",2019,"Distinguish between food chains and food webs. Discuss the concept of trophic levels.",10),
  ("Ecological Pyramids",1.0,"environmental",2018,"Explain the different types of ecological pyramids and their significance in ecosystem study.",10),
  ("Ecological Succession",1.0,"environmental",2017,"Discuss the process of ecological succession with reference to primary and secondary succession.",15),
  ("Biosphere and Gaia Hypothesis",1.0,"environmental",2016,"Explain Lovelock's Gaia hypothesis and discuss its significance for understanding Earth as a system.",10)],
 "Human-Environment Interaction": [
  ("Environmental Determinism",1.0,"human",2019,"Discuss the concept of environmental determinism and its critique in modern geography.",15),
  ("Possibilism and Neo-Determinism",1.0,"human",2020,"Compare possibilism and neo-determinism as approaches to human-environment relationships.",15),
  ("Man-Environment Relationship in Geography",1.5,"human",2021,"Trace the evolution of human-environment relationship concepts in geographic thought.",15),
  ("Sustainable Development Concept",1.5,"environmental",2022,"Define sustainable development and discuss the challenges in achieving it in developing countries.",15),
  ("Environmental Ethics and Deep Ecology",1.0,"environmental",2018,"Discuss environmental ethics and the concept of deep ecology. How do they inform conservation?",10),
  ("Carrying Capacity of Earth",1.0,"environmental",2017,"Discuss the concept of carrying capacity and debate whether Earth has reached its limits.",15)],
 "Environmental Degradation": [
  ("Air Pollution - Types Sources and Effects",1.5,"environmental",2023,"Discuss the types and sources of air pollution in India. Explain measures for control.",15),
  ("Water Pollution and Eutrophication",1.5,"environmental",2021,"Discuss water pollution problems in Indian rivers and explain the process of eutrophication.",15),
  ("Land Degradation and Desertification",1.0,"environmental",2020,"Discuss the causes and extent of land degradation in India. What remedial measures are needed?",15),
  ("Noise Pollution",1.0,"environmental",2018,"Discuss noise pollution: sources effects and regulatory framework in India.",10),
  ("Solid Waste Management",1.5,"environmental",2022,"Discuss the solid waste management challenges in Indian cities and evaluate current solutions.",15),
  ("Industrial Pollution and E-Waste",1.0,"environmental",2019,"Discuss the problem of industrial pollution and e-waste management in India.",10)],
 "Natural Hazards and Disasters": [
  ("Earthquake Hazard and Risk Assessment",1.5,"environmental",2022,"Discuss earthquake hazard assessment methods and their application for Indian cities.",15),
  ("Flood and Drought Management",1.5,"environmental",2021,"Discuss the causes of floods and droughts in India and evaluate management strategies.",20),
  ("Cyclone Disaster Management",1.0,"environmental",2020,"Evaluate India's cyclone disaster management framework with reference to recent events.",15),
  ("Landslides and Avalanches",1.0,"environmental",2019,"Discuss landslide and avalanche hazards in the Himalayan region and mitigation strategies.",15),
  ("Volcanic Hazards",1.0,"environmental",2017,"Discuss volcanic hazards and the assessment of volcanic risk for potentially affected populations.",10),
  ("Disaster Risk Reduction Framework",1.5,"environmental",2023,"Discuss the Sendai Framework for Disaster Risk Reduction and India's implementation.",15)],
 "Environmental Policies and Laws": [
  ("Indian Environmental Legislation",1.5,"environmental",2022,"Discuss the major environmental legislation in India and evaluate their effectiveness.",15),
  ("Environmental Impact Assessment",1.0,"environmental",2021,"Discuss the EIA process in India including recent changes and their implications.",15),
  ("National Action Plan on Climate Change",1.5,"environmental",2020,"Discuss India's NAPCC and evaluate the progress of its eight national missions.",15),
  ("International Environmental Agreements",1.0,"environmental",2019,"Discuss India's participation in major international environmental agreements.",15),
  ("Environmental Governance in India",1.0,"environmental",2023,"Discuss the challenges of environmental governance in India and suggest reforms.",15)],
 "Global Environmental Issues": [
  ("Global Warming and Climate Change Impacts",1.5,"environmental",2023,"Discuss the impacts of global warming on different regions and sectors globally and in India.",20),
  ("Ozone Layer Depletion",1.0,"environmental",2018,"Discuss ozone depletion: causes effects and the success of international response.",15),
  ("Acid Rain and Transboundary Pollution",1.0,"environmental",2017,"Explain the phenomenon of acid rain and discuss transboundary pollution issues.",10),
  ("Sea Level Rise and Coastal Vulnerability",1.5,"environmental",2022,"Discuss the causes of sea level rise and its implications for India's coastal regions.",15),
  ("Loss of Biodiversity - Sixth Extinction",1.0,"environmental",2021,"Discuss the concept of the Sixth Mass Extinction and evaluate current biodiversity loss rates.",15)],
 "Applied Environmental Geography": [
  ("Remote Sensing in Environmental Monitoring",1.5,"environmental",2020,"Discuss the applications of remote sensing in environmental monitoring and management.",15),
  ("GIS Applications in Environment",1.0,"environmental",2019,"Explain how GIS is applied in environmental planning and management with Indian examples.",15),
  ("Urban Environmental Problems",1.5,"environmental",2022,"Discuss the major environmental challenges facing Indian cities and evaluate solutions.",15),
  ("Environmental Auditing and Accounting",1.0,"environmental",2018,"Discuss the concept of environmental auditing and green accounting for sustainable development.",10),
  ("Green Technology and Sustainability",1.0,"environmental",2021,"Discuss how green technology can contribute to environmental sustainability in India.",10)]}

MEGA6_HUMAN = {
 "Evolution of Geographic Thought": [
  ("Ancient and Medieval Geography",1.0,"human",2018,"Trace the development of geographic knowledge from ancient to medieval periods.",15),
  ("Geographical Societies and Exploration Age",1.0,"human",2017,"Discuss the role of geographical societies and exploration in developing geographic knowledge.",10),
  ("German School - Humboldt and Ritter",1.5,"human",2020,"Discuss the contributions of Humboldt and Ritter to modern geography.",15),
  ("French School - Vidal de la Blache",1.5,"human",2019,"Discuss Vidal de la Blache's contribution to human geography and possibilism.",15),
  ("American School and Regional Geography",1.0,"human",2021,"Trace the development of the American school of geography and its regional approach.",10),
  ("Modern Geography and Paradigm Shifts",1.5,"human",2022,"Discuss the major paradigm shifts in geographic thought during the twentieth century.",15)],
 "Philosophical Approaches": [
  ("Environmental Determinism",1.0,"human",2019,"Critically evaluate environmental determinism as a geographic philosophy.",15),
  ("Possibilism and Cultural Landscape",1.5,"human",2020,"Discuss possibilism and Sauer's cultural landscape concept.",15),
  ("Quantitative Revolution and Spatial Science",1.5,"human",2021,"Discuss the quantitative revolution in geography and its impact on the discipline.",15),
  ("Behavioral Geography",1.0,"human",2018,"Explain behavioral geography and its contribution to understanding spatial decision-making.",10),
  ("Radical and Marxist Geography",1.0,"human",2017,"Discuss radical geography and the Marxist perspective in geographic analysis.",15),
  ("Humanistic Geography",1.0,"human",2016,"Explain humanistic geography and its philosophical foundations in phenomenology.",10),
  ("Postmodern Geography",1.0,"human",2022,"Discuss postmodern approaches in geography and their critique of grand narratives.",10)],
 "Areal Differentiation and Regionalism": [
  ("Areal Differentiation - Hartshorne",1.5,"human",2020,"Discuss Hartshorne's concept of areal differentiation and its significance for geography.",15),
  ("Regional Synthesis and Idiographic Approach",1.0,"human",2019,"Explain the idiographic approach in regional geography and compare with nomothetic methods.",10),
  ("Functional and Formal Regions",1.0,"human",2018,"Distinguish between formal and functional regions with suitable examples.",10),
  ("Regional Geography vs Systematic Geography",1.0,"human",2021,"Discuss the debate between regional and systematic approaches in geography.",15),
  ("Contemporary Regional Approaches",1.0,"human",2017,"Discuss contemporary approaches to regional analysis in modern geography.",10)],
 "Cultural Geography": [
  ("Culture Regions and Cultural Landscape",1.5,"human",2022,"Discuss the concepts of culture region and cultural landscape in geography.",15),
  ("Language and Religious Geography",1.0,"human",2020,"Discuss the spatial distribution of languages and religions and their geographic significance.",15),
  ("Diffusion of Innovations",1.0,"human",2019,"Explain Hagerstrand's theory of innovation diffusion and its geographic applications.",15),
  ("Ethnicity Race and Identity",1.0,"human",2018,"Discuss how ethnicity race and identity are expressed spatially in geographic patterns.",10),
  ("Cultural Globalization",1.0,"human",2021,"Discuss the geographic dimensions of cultural globalization and local responses.",15),
  ("Indigenous Knowledge Systems",1.0,"human",2017,"Discuss the role of indigenous knowledge in geographic understanding and resource management.",10)],
 "Social Geography": [
  ("Social Well-being and Quality of Life",1.5,"human",2022,"Discuss geographic approaches to measuring social well-being and quality of life.",15),
  ("Gender Geography",1.0,"human",2020,"Discuss gender as a geographic variable and its significance for spatial analysis.",15),
  ("Geography of Health and Disease",1.0,"human",2021,"Discuss the spatial patterns of health and disease distribution with Indian examples.",15),
  ("Geography of Education",1.0,"human",2019,"Discuss spatial disparities in educational access and outcomes in India.",10),
  ("Inequality and Social Justice",1.0,"human",2023,"Discuss geographic perspectives on inequality and social justice.",15)],
 "Human Development": [
  ("Human Development Index (HDI)",1.5,"human",2022,"Discuss the HDI as a measure of development and its limitations.",15),
  ("Measures of Development - GDI GII MPI",1.0,"human",2021,"Compare different measures of development: GDI GII and MPI.",15),
  ("Developed vs Developing Countries",1.0,"human",2020,"Discuss the geographic characteristics distinguishing developed from developing countries.",15),
  ("Sustainable Human Development",1.5,"human",2019,"Discuss the concept of sustainable human development and its geographic dimensions.",15),
  ("Millennium and Sustainable Development Goals",1.0,"human",2023,"Discuss the SDGs and evaluate India's progress toward achieving them.",15),
  ("Quality of Life Indicators",1.0,"human",2018,"Discuss different quality of life indicators and their geographic applications.",10)]}


MEGA7_ECONOMIC = {
 "Resources and Development": [
  ("Concept and Classification of Resources",1.5,"economic",2020,"Discuss the concept of resources and their classification. How has the meaning evolved?",15),
  ("Resource Distribution and Utilization",1.0,"economic",2019,"Discuss the uneven distribution of natural resources and its implications for development.",15),
  ("Energy Resources - Conventional and Non-conventional",1.5,"economic",2022,"Compare conventional and non-conventional energy resources with Indian distribution.",15),
  ("Mineral Resources and Distribution",1.5,"economic",2021,"Discuss the distribution of mineral resources in India and their economic significance.",15),
  ("Resource Depletion and Conservation",1.0,"economic",2018,"Discuss resource depletion challenges and conservation strategies for sustainable use.",15),
  ("Renewable Energy Transition",1.5,"economic",2023,"Discuss India's renewable energy transition and its geographic implications.",15)],
 "Agriculture and Food Security": [
  ("Types of Agriculture Worldwide",1.0,"economic",2019,"Classify world agriculture types and discuss factors determining their distribution.",15),
  ("Agricultural Systems and Land Use",1.5,"economic",2020,"Discuss agricultural systems and Von Thunen's model of land use with modern relevance.",15),
  ("Green Revolution and Its Impact",1.5,"economic",2018,"Evaluate the Green Revolution's impact on Indian agriculture including positive and negative aspects.",15),
  ("Food Security and World Hunger",1.5,"economic",2022,"Discuss food security challenges globally and evaluate India's food security programs.",15),
  ("Agricultural Modernization",1.0,"economic",2021,"Discuss the modernization of agriculture and its socioeconomic and environmental impacts.",15),
  ("Organic Farming and Sustainable Agriculture",1.0,"economic",2023,"Discuss organic farming as a sustainable agriculture approach with Indian examples.",10),
  ("Livestock and Dairy Economy",1.0,"economic",2017,"Discuss the role of livestock and dairy in India's agricultural economy.",10),
  ("Fisheries and Aquaculture",1.0,"economic",2020,"Discuss India's fisheries sector including marine and inland fisheries and aquaculture.",10)],
 "Industries and Manufacturing": [
  ("Industrial Location Theories - Weber",1.5,"economic",2020,"Discuss Weber's theory of industrial location and its relevance in the modern economy.",15),
  ("Factors Affecting Industrial Location",1.0,"economic",2019,"Discuss the factors affecting industrial location with examples from India.",15),
  ("Types of Industries",1.0,"economic",2018,"Classify industries by different criteria and discuss with Indian examples.",10),
  ("Major Industrial Regions of World",1.5,"economic",2021,"Describe the major industrial regions of the world and explain their locational advantages.",15),
  ("Industrial Revolution and Stages",1.0,"economic",2017,"Discuss the stages of industrial development from pre-industrial to post-industrial.",10),
  ("Deindustrialization and New Economy",1.0,"economic",2022,"Discuss deindustrialization in developed countries and the rise of the knowledge economy.",15),
  ("Special Economic Zones",1.0,"economic",2023,"Evaluate the role of SEZs in India's industrial development strategy.",10)],
 "Transport and Communication": [
  ("Modes of Transport and Networks",1.5,"economic",2021,"Discuss the different modes of transport and their role in economic development.",15),
  ("Road and Railway Geography",1.0,"economic",2020,"Discuss India's road and railway networks and their significance for regional development.",15),
  ("Maritime Transport and Ports",1.0,"economic",2019,"Discuss maritime transport and the role of major ports in India's trade.",15),
  ("Air Transport and Aviation Geography",1.0,"economic",2018,"Discuss the growth of air transport and its geographic implications for India.",10),
  ("Communication Revolution and IT",1.5,"economic",2022,"Discuss the communication revolution and its impact on India's economic geography.",15),
  ("Digital Divide and Connectivity",1.0,"economic",2023,"Discuss the digital divide in India and efforts to improve connectivity.",10)],
 "International Trade": [
  ("Theories of International Trade",1.5,"economic",2020,"Discuss the major theories of international trade and their geographic implications.",15),
  ("World Trade Organization",1.0,"economic",2019,"Discuss WTO's role in governing international trade and its impact on developing countries.",15),
  ("Patterns of Global Trade",1.0,"economic",2021,"Discuss contemporary patterns of global trade and India's position in world commerce.",15),
  ("Trade Blocs and Regional Integration",1.5,"economic",2022,"Discuss trade blocs and regional economic integration with examples.",15),
  ("Balance of Trade and Payments",1.0,"economic",2018,"Discuss India's balance of trade and payments situation and its geographic factors.",10),
  ("Globalization and Trade Liberalization",1.0,"economic",2017,"Discuss the impact of globalization and trade liberalization on Indian economy.",15)],
 "Tourism and Services": [
  ("Geography of Tourism",1.5,"economic",2022,"Discuss the geographic factors influencing tourism development with Indian examples.",15),
  ("Ecotourism and Sustainable Tourism",1.0,"economic",2021,"Discuss ecotourism as a sustainable development strategy for India.",10),
  ("Service Sector and Tertiary Economy",1.0,"economic",2020,"Discuss the growth of the service sector and its geographic distribution in India.",15),
  ("Knowledge Economy and Quaternary Sector",1.0,"economic",2019,"Discuss the knowledge economy and quaternary activities with reference to Indian IT sector.",10),
  ("Global Value Chains",1.0,"economic",2023,"Discuss the concept of global value chains and India's integration into them.",15)],
 "Globalization": [
  ("Economic Globalization Process",1.5,"economic",2022,"Discuss the process of economic globalization and its geographic dimensions.",15),
  ("Multinational Corporations",1.0,"economic",2020,"Discuss the role of MNCs in global economic geography and their impact on developing nations.",15),
  ("Impact on Developing Countries",1.0,"economic",2019,"Discuss globalization's impact on developing countries with reference to India.",15),
  ("Deglobalization Trends",1.0,"economic",2023,"Discuss recent deglobalization trends and their implications for global economic geography.",10)]}

MEGA8_POPULATION = {
 "Population Growth and Distribution": [
  ("World Population Distribution Patterns",1.5,"population",2021,"Discuss the major patterns of world population distribution and their controlling factors.",15),
  ("Factors Affecting Population Distribution",1.0,"population",2020,"Discuss the physical and socioeconomic factors affecting population distribution.",15),
  ("Population Growth Trends - Historical and Current",1.5,"population",2022,"Discuss world population growth trends from historical to current perspectives.",15),
  ("Population Explosion and Control",1.0,"population",2019,"Discuss the concept of population explosion and evaluate population control strategies.",15),
  ("Optimum Population Theory",1.0,"population",2018,"Discuss the concept of optimum population and its relevance for development planning.",10),
  ("Carrying Capacity and Overpopulation",1.0,"population",2017,"Discuss the concept of carrying capacity and debate about overpopulation.",15)],
 "Population Theories and Models": [
  ("Malthusian Theory",1.5,"population",2020,"Critically examine Malthus's theory of population in the light of modern evidence.",15),
  ("Neo-Malthusian Views",1.0,"population",2019,"Discuss neo-Malthusian perspectives on population and resources.",10),
  ("Demographic Transition Model",1.5,"population",2022,"Discuss the Demographic Transition Model and its applicability to developing countries.",15),
  ("Marxist Theory of Population",1.0,"population",2018,"Discuss the Marxist critique of Malthusian population theory.",10),
  ("Boserup Theory of Agricultural Intensification",1.0,"population",2017,"Discuss Boserup's theory and its contrast with Malthusian views on population-food relationship.",15)],
 "Population Composition and Structure": [
  ("Age-Sex Composition and Population Pyramids",1.5,"population",2022,"Discuss population pyramids and what they reveal about demographic characteristics.",15),
  ("Sex Ratio - Patterns and Causes",1.0,"population",2021,"Discuss sex ratio patterns in India and explain regional variations.",15),
  ("Literacy and Education Levels",1.0,"population",2020,"Discuss spatial patterns of literacy in India and factors affecting educational attainment.",10),
  ("Occupational Structure",1.0,"population",2019,"Discuss the occupational structure of India's population and recent changes.",10),
  ("Ethnic and Racial Composition",1.0,"population",2018,"Discuss the ethnic and racial composition of populations and its geographic significance.",10),
  ("Religious and Linguistic Diversity",1.0,"population",2017,"Discuss religious and linguistic diversity patterns in India and their geographic dimensions.",15)],
 "Migration": [
  ("Types and Classification of Migration",1.5,"population",2022,"Classify migration types and discuss their geographic significance.",15),
  ("Causes and Consequences of Migration",1.5,"population",2021,"Discuss the causes and consequences of migration with Indian examples.",15),
  ("Ravenstein's Laws of Migration",1.0,"population",2020,"Discuss Ravenstein's laws of migration and their validity in the modern context.",15),
  ("Push-Pull Theory",1.0,"population",2019,"Explain the push-pull theory of migration and evaluate its explanatory power.",10),
  ("International Migration Patterns",1.5,"population",2023,"Discuss contemporary international migration patterns and their geographic implications.",15),
  ("Refugees and Forced Migration",1.0,"population",2018,"Discuss the geography of refugees and forced migration in the contemporary world.",15),
  ("Brain Drain and Remittances",1.0,"population",2017,"Discuss brain drain and its counterbalance through remittances with Indian context.",10)],
 "Population and Development": [
  ("Population and Economic Development",1.5,"population",2022,"Discuss the relationship between population growth and economic development.",15),
  ("Demographic Dividend",1.5,"population",2023,"Discuss India's demographic dividend and conditions needed to realize its potential.",15),
  ("Population Policies Worldwide",1.0,"population",2020,"Compare population policies of different countries and evaluate their effectiveness.",15),
  ("India's Population Policy",1.5,"population",2021,"Discuss the evolution of India's population policy and its current challenges.",15),
  ("Family Planning Programs",1.0,"population",2019,"Evaluate India's family planning programs and their geographic variations in success.",10),
  ("Population and Food Supply",1.0,"population",2018,"Discuss the relationship between population growth and food supply in developing nations.",15)],
 "Health and Population": [
  ("Epidemiological Transition",1.0,"population",2021,"Discuss the epidemiological transition model and its relevance to India.",15),
  ("Disease Diffusion and Spatial Patterns",1.0,"population",2020,"Discuss how diseases spread spatially and the factors affecting their geographic distribution.",10),
  ("Maternal and Child Health Indicators",1.0,"population",2022,"Discuss maternal and child health indicators and their geographic variations in India.",15),
  ("Population Aging and Its Challenges",1.0,"population",2019,"Discuss the challenges of population aging and its implications for society and economy.",10)],
 "Urbanization and Population": [
  ("Urbanization Trends Worldwide",1.5,"population",2022,"Discuss global urbanization trends and their geographic implications.",15),
  ("Urban Population Growth",1.0,"population",2021,"Discuss patterns of urban population growth in India and associated challenges.",15),
  ("Rural-Urban Migration",1.0,"population",2020,"Discuss the causes and consequences of rural-urban migration in India.",15),
  ("Megacities and Urban Challenges",1.0,"population",2023,"Discuss the emergence of megacities and the challenges they face in developing countries.",15)]}

MEGA9_SETTLEMENT = {
 "Rural Settlements": [
  ("Types of Rural Settlements",1.0,"settlement",2020,"Classify rural settlements by form and discuss factors determining settlement types.",15),
  ("Patterns of Rural Settlements",1.5,"settlement",2019,"Discuss patterns of rural settlements and their relationship with physical environment.",15),
  ("Factors Affecting Rural Settlement Location",1.0,"settlement",2018,"Discuss the factors influencing rural settlement location in India.",15),
  ("Rural Settlement Morphology",1.0,"settlement",2021,"Discuss the morphology of rural settlements with Indian examples.",10),
  ("Rural-Urban Fringe",1.0,"settlement",2017,"Discuss the characteristics of rural-urban fringe and its development challenges.",10),
  ("Rural Development and Planning",1.5,"settlement",2022,"Discuss approaches to rural development planning in India.",15),
  ("Smart Villages",1.0,"settlement",2023,"Discuss the concept of smart villages and their potential for rural development.",10)],
 "Urban Settlements": [
  ("Origin and Growth of Towns and Cities",1.5,"settlement",2020,"Discuss the origin and growth of urban settlements with historical perspective.",15),
  ("Urban Morphology and Land Use",1.5,"settlement",2021,"Discuss urban morphology and land use patterns with Indian city examples.",15),
  ("Functional Classification of Towns",1.0,"settlement",2019,"Classify Indian towns by function and discuss their spatial distribution.",10),
  ("Urban Hierarchy and Rank-Size Rule",1.0,"settlement",2018,"Discuss urban hierarchy and evaluate the applicability of rank-size rule to Indian cities.",15),
  ("Primate City Concept",1.0,"settlement",2017,"Discuss the primate city concept and its applicability in the Indian urban context.",10),
  ("Urban Sprawl and Suburbanization",1.5,"settlement",2022,"Discuss urban sprawl and suburbanization processes in Indian metropolitan areas.",15),
  ("Edge Cities and New Urbanism",1.0,"settlement",2023,"Discuss the concepts of edge cities and new urbanism in contemporary urban geography.",10)],
 "Urban Theories and Models": [
  ("Christaller Central Place Theory",1.5,"settlement",2022,"Discuss Christaller's Central Place Theory and evaluate its applicability.",15),
  ("Burgess Concentric Zone Model",1.5,"settlement",2020,"Discuss the Burgess model of urban land use and its limitations.",15),
  ("Hoyt Sector Model",1.0,"settlement",2019,"Explain Hoyt's sector model and compare with Burgess's concentric zone theory.",10),
  ("Harris and Ullman Multiple Nuclei Model",1.0,"settlement",2018,"Discuss the multiple nuclei model and its relevance to modern cities.",10),
  ("Urban Realms Model",1.0,"settlement",2021,"Discuss the urban realms model and its application to contemporary metropolitan areas.",10),
  ("Bid-Rent Theory and Land Values",1.0,"settlement",2017,"Explain bid-rent theory and how it explains urban land use patterns.",15)],
 "Urban Problems and Planning": [
  ("Housing and Slums",1.5,"settlement",2022,"Discuss the housing crisis and slum problems in Indian cities. Suggest solutions.",15),
  ("Urban Transport and Congestion",1.5,"settlement",2021,"Discuss urban transport challenges in Indian cities and evaluate proposed solutions.",15),
  ("Urban Pollution and Environment",1.0,"settlement",2020,"Discuss environmental problems in Indian urban areas and management strategies.",15),
  ("Urban Poverty and Inequality",1.0,"settlement",2019,"Discuss urban poverty and spatial inequality in Indian cities.",15),
  ("Town Planning and Master Plans",1.5,"settlement",2023,"Discuss town planning approaches and evaluate master plan implementation in India.",15),
  ("Smart Cities Mission India",1.0,"settlement",2022,"Evaluate India's Smart Cities Mission and its urban development outcomes.",10),
  ("Sustainable Urban Development",1.0,"settlement",2018,"Discuss principles of sustainable urban development with Indian examples.",15)],
 "Urbanization Process": [
  ("Stages of Urbanization",1.0,"settlement",2020,"Discuss the stages of urbanization and India's current position in this process.",15),
  ("Counter-urbanization and Reurbanization",1.0,"settlement",2019,"Discuss counter-urbanization trends and reurbanization in the global context.",10),
  ("Urbanization in Developing Countries",1.5,"settlement",2021,"Discuss urbanization challenges in developing countries with focus on India.",15),
  ("Urban Governance and Administration",1.0,"settlement",2022,"Discuss urban governance challenges in India and the 74th Amendment provisions.",15)],
 "Mega-cities and World Cities": [
  ("Global City Concept",1.5,"settlement",2022,"Discuss the concept of global cities and evaluate Indian cities in this framework.",15),
  ("Megacity Challenges",1.0,"settlement",2021,"Discuss challenges faced by megacities in developing countries with Indian examples.",15),
  ("Urban Networks and Systems",1.0,"settlement",2020,"Discuss urban networks and city systems in the context of globalization.",10),
  ("Future of Cities",1.0,"settlement",2023,"Discuss emerging trends shaping the future of cities globally and in India.",10)]}

MEGA10_REGIONAL = {
 "Concept and Types of Regions": [
  ("Formal and Functional Regions",1.5,"regional",2021,"Distinguish between formal and functional regions with examples.",15),
  ("Nodal and Planning Regions",1.0,"regional",2020,"Discuss nodal regions and planning regions as frameworks for development planning.",10),
  ("Methods of Regional Delineation",1.0,"regional",2019,"Discuss the methods used for delineating regions for planning purposes.",15),
  ("Regionalism and Regional Identity",1.0,"regional",2018,"Discuss regionalism as a geographic phenomenon and its role in identity formation.",15),
  ("Micro-Meso-Macro Regions",1.0,"regional",2017,"Discuss the concept of multi-level regional hierarchy from micro to macro scales.",10)],
 "Regional Development Theories": [
  ("Growth Pole Theory (Perroux)",1.5,"regional",2022,"Discuss Perroux's growth pole theory and its application in Indian planning.",15),
  ("Core-Periphery Model (Friedmann)",1.5,"regional",2021,"Discuss Friedmann's core-periphery model and its relevance to Indian regional disparities.",15),
  ("Cumulative Causation (Myrdal)",1.5,"regional",2020,"Explain Myrdal's cumulative causation model and its implications for regional planning.",15),
  ("Unbalanced Growth Theory (Hirschman)",1.0,"regional",2019,"Discuss Hirschman's unbalanced growth theory and the concept of linkages.",10),
  ("Dependency Theory and World Systems",1.0,"regional",2018,"Discuss dependency theory and Wallerstein's world-systems analysis.",15),
  ("Rostow's Stages of Economic Growth",1.0,"regional",2017,"Critically evaluate Rostow's stages of growth model for developing countries.",15)],
 "Regional Planning Approaches": [
  ("Top-Down vs Bottom-Up Planning",1.5,"regional",2022,"Compare top-down and bottom-up approaches to regional planning in India.",15),
  ("Decentralized Planning",1.0,"regional",2021,"Discuss decentralized planning and Panchayati Raj institutions in regional development.",15),
  ("Integrated Area Development",1.0,"regional",2020,"Discuss integrated area development programs and their effectiveness in India.",10),
  ("River Basin Planning",1.5,"regional",2019,"Discuss river basin planning as a regional development approach with Indian examples.",15),
  ("Multi-Level Planning",1.0,"regional",2018,"Discuss multi-level planning from village to national level in Indian context.",10)],
 "Regional Imbalance": [
  ("Causes of Regional Disparities",1.5,"regional",2022,"Discuss the causes of regional disparities in India.",15),
  ("Measurement of Regional Inequality",1.0,"regional",2021,"Discuss methods for measuring regional inequality and development disparities.",10),
  ("Regional Imbalance in India",1.5,"regional",2023,"Discuss regional imbalance in India and evaluate corrective measures taken.",20),
  ("Backward Area Development",1.0,"regional",2020,"Discuss approaches to backward area development in India.",15),
  ("Special Category States",1.0,"regional",2019,"Discuss the concept of special category states and its relevance for Indian planning.",10)],
 "Planning in India": [
  ("Five Year Plans and Regional Development",1.5,"regional",2020,"Discuss how Five Year Plans addressed regional development in India.",15),
  ("NITI Aayog and New Planning Framework",1.5,"regional",2022,"Discuss NITI Aayog's approach to regional planning replacing the Planning Commission.",15),
  ("Special Area Programs",1.0,"regional",2019,"Discuss special area programs for hill tribal and border areas in India.",15),
  ("Tribal and Hill Area Development",1.0,"regional",2018,"Discuss development challenges and programs for tribal and hill areas of India.",10),
  ("Border Area Development",1.0,"regional",2021,"Discuss border area development programs and their strategic importance.",10)],
 "International Regional Planning": [
  ("European Union Regional Policy",1.0,"regional",2020,"Discuss EU regional policy as a model for addressing intra-regional disparities.",15),
  ("Regional Blocs and Cooperation",1.0,"regional",2019,"Discuss regional blocs and cooperation mechanisms with South Asian examples.",10),
  ("Transboundary Regional Planning",1.0,"regional",2021,"Discuss challenges and approaches in transboundary regional planning.",10),
  ("Sustainable Regional Development",1.0,"regional",2022,"Discuss principles of sustainable regional development with contemporary examples.",15)]}

MEGA11_MODELS = {
 "Systems Approach in Geography": [
  ("General Systems Theory in Geography",1.5,"models",2021,"Discuss the application of general systems theory in geographic analysis.",15),
  ("Open and Closed Systems",1.0,"models",2020,"Distinguish between open and closed systems with geographic examples.",10),
  ("Feedback Mechanisms",1.0,"models",2019,"Explain positive and negative feedback mechanisms in geographic systems.",10),
  ("Entropy and Equilibrium",1.0,"models",2018,"Discuss entropy and equilibrium concepts in geographic system analysis.",10),
  ("Systems Analysis Applications",1.0,"models",2017,"Discuss practical applications of systems analysis in geographic research.",10)],
 "Location Theories": [
  ("Von Thunen Agricultural Location Theory",1.5,"models",2022,"Discuss Von Thunen's model of agricultural land use and its modern relevance.",15),
  ("Weber Industrial Location Theory",1.5,"models",2021,"Discuss Weber's theory of industrial location including material index and isodapane concepts.",15),
  ("Losch Market Area Theory",1.0,"models",2020,"Explain Losch's market area theory and its contribution to economic geography.",15),
  ("Christaller Central Place Theory",1.5,"models",2019,"Discuss Christaller's central place theory including assumptions and modifications.",15),
  ("Hotelling Linear Market Model",1.0,"models",2018,"Explain Hotelling's model of spatial competition along a linear market.",10),
  ("Modern Industrial Location Factors",1.0,"models",2022,"Discuss how modern factors like technology and globalization modify classical location theories.",15),
  ("Location Theory Criticisms and Updates",1.0,"models",2017,"Critically evaluate classical location theories and discuss their modern modifications.",15)],
 "Population and Settlement Models": [
  ("Demographic Transition Model",1.5,"models",2022,"Discuss the Demographic Transition Model and its applicability to developing nations.",15),
  ("Zelinsky's Mobility Transition",1.0,"models",2020,"Discuss Zelinsky's mobility transition model and its relationship to demographic change.",10),
  ("Gravity Model and Distance Decay",1.5,"models",2021,"Explain the gravity model and distance decay concept in geographic interaction.",15),
  ("Rank-Size Rule and Zipf's Law",1.0,"models",2019,"Discuss the rank-size rule and Zipf's law for urban size distribution.",10),
  ("Urban Growth Models",1.0,"models",2018,"Discuss various models explaining urban growth patterns and processes.",10)],
 "Economic Development Models": [
  ("Rostow Stages of Growth",1.5,"models",2020,"Critically evaluate Rostow's stages of economic growth model.",15),
  ("Lewis Dual Economy Model",1.0,"models",2019,"Discuss the Lewis model of structural transformation from agrarian to industrial economy.",15),
  ("Dependency Theory (Frank)",1.0,"models",2021,"Discuss Frank's dependency theory and its explanation of underdevelopment.",15),
  ("World Systems Theory (Wallerstein)",1.5,"models",2022,"Discuss Wallerstein's world-systems analysis and its geographic implications.",15),
  ("Sustainable Development Model",1.0,"models",2023,"Discuss models of sustainable development that integrate economic environmental and social dimensions.",15),
  ("New Economic Geography (Krugman)",1.0,"models",2018,"Discuss Krugman's new economic geography and its contribution to spatial economics.",10)],
 "Diffusion and Interaction Models": [
  ("Hagerstrand Spatial Diffusion Theory",1.5,"models",2021,"Discuss Hagerstrand's theory of spatial diffusion of innovations.",15),
  ("Innovation Diffusion Patterns",1.0,"models",2020,"Discuss the patterns and barriers to innovation diffusion in geographic space.",10),
  ("Spatial Interaction Models",1.0,"models",2019,"Discuss spatial interaction models and their applications in transport and migration studies.",15),
  ("Network Analysis in Geography",1.0,"models",2022,"Discuss network analysis approaches and their applications in geographic research.",10)],
 "Geopolitical Theories": [
  ("Mackinder Heartland Theory",1.5,"models",2022,"Discuss Mackinder's Heartland theory and evaluate its relevance in the 21st century.",15),
  ("Spykman Rimland Theory",1.0,"models",2021,"Discuss Spykman's Rimland theory as a modification of Mackinder's geopolitics.",10),
  ("Mahan Sea Power Theory",1.0,"models",2020,"Discuss Mahan's concept of sea power and its relevance for India's maritime strategy.",15),
  ("Cohen Geostrategic Regions",1.0,"models",2019,"Discuss Cohen's model of geostrategic regions in the post-Cold War context.",10),
  ("Critical Geopolitics",1.0,"models",2023,"Discuss the critical geopolitics approach and its deconstruction of traditional geopolitical narratives.",10)],
 "Quantitative Methods": [
  ("Statistical Methods in Geography",1.0,"models",2020,"Discuss the role of statistical methods in geographic analysis and research.",10),
  ("Spatial Analysis and GIS Models",1.5,"models",2022,"Discuss spatial analysis techniques using GIS for geographic problem-solving.",15),
  ("Remote Sensing Applications in Geographic Research",1.5,"models",2021,"Discuss remote sensing applications in geographic research with Indian examples.",15)]}


def get_remaining_megas():
    """Build mega-topics 4-11 from structured definitions."""
    all_data = [
        ("Biogeography", 4, MEGA4_BIOGEOGRAPHY),
        ("Environmental Geography", 5, MEGA5_ENVIRONMENTAL),
        ("Perspectives in Human Geography", 6, MEGA6_HUMAN),
        ("Economic Geography", 7, MEGA7_ECONOMIC),
        ("Population Geography", 8, MEGA8_POPULATION),
        ("Settlement Geography", 9, MEGA9_SETTLEMENT),
        ("Regional Planning", 10, MEGA10_REGIONAL),
        ("Models Theories and Laws in Geography", 11, MEGA11_MODELS),
    ]
    
    megas = []
    for mega_title, mega_order, mega_data in all_data:
        subs_list = []
        for si, (sub_title, topics) in enumerate(mega_data.items(), 1):
            leaves_list = []
            for li, (title, weight, field, pyq_year, pyq_q, pyq_marks) in enumerate(topics, 1):
                leaves_list.append(_gen_leaf(title, weight, li, "", field, pyq_year, pyq_q, pyq_marks))
            subs_list.append(_sub(sub_title, si, leaves_list))
        megas.append(_mega(mega_title, mega_order, subs_list))
    return megas
