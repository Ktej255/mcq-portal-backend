
import sys
import os
sys.path.insert(0, '.')

from app.db.session import SessionLocal
from app.models.domain import Question, Test
from sqlalchemy import text

def insert_manual_questions():
    db = SessionLocal()
    
    questions_to_add = [
        {
            "test_id": 6, # Batch 5
            "topic_id": 4,
            "text": "Consider the following statements about the Assertion-Reason format in ecology:\n\nAssertion (A): Tropical rainforests have very poor, nutrient-deficient soils despite supporting the world's richest biodiversity.\n\nReason (R): In tropical rainforests, nutrients are rapidly cycled and stored mostly in the living biomass rather than in the soil, because warm and humid conditions accelerate decomposition and immediate uptake by plant roots.",
            "options": {
                "A": "Both A and R are true, and R is the correct explanation of A",
                "B": "Both A and R are true, but R is NOT the correct explanation of A",
                "C": "A is true but R is false",
                "D": "A is false but R is true"
            },
            "correct": "A",
            "q_num": "Q230"
        },
        {
            "test_id": 7, # Batch 6
            "topic_id": 4,
            "text": "Consider the following statements about the Ramsar Convention's Wise Use principle:\n\nAssertion (A): The Ramsar Convention does not prohibit all human use of designated wetland sites.\n\nReason (R): The guiding principle of the Ramsar Convention is 'Wise Use', which is defined as the maintenance of the ecological character of wetlands achieved through the implementation of ecosystem approaches in the context of sustainable development.",
            "options": {
                "A": "Both A and R are true, and R is the correct explanation of A",
                "B": "Both A and R are true, but R is NOT the correct explanation of A",
                "C": "A is true but R is false",
                "D": "A is false but R is true"
            },
            "correct": "A",
            "q_num": "Q259"
        },
        {
            "test_id": 7, # Batch 6
            "topic_id": 4,
            "text": "Consider the following statements about the National Peatland Restoration and Conservation Initiative:\n\nAssertion (A): India has limited tropical peatland compared to Southeast Asia and Central Africa, yet peatland conservation is relevant to India's NDC commitments.\n\nReason (R): India's NDC targets creating additional carbon sinks of 2.5 to 3 billion tonnes through forests and tree cover, and high-altitude Himalayan wetlands and shoal grasslands, though not classical peatlands, store significant soil carbon whose conservation contributes to this target.",
            "options": {
                "A": "Both A and R are true, and R is the correct explanation of A",
                "B": "Both A and R are true, but R is NOT the correct explanation of A",
                "C": "A is true but R is false",
                "D": "A is false but R is true"
            },
            "correct": "A",
            "q_num": "Q278"
        },
        {
            "test_id": 8, # Batch 7
            "topic_id": 4,
            "text": "Consider the following statements about Peat and Tropical Peatland:\n\nAssertion (A): Burning of tropical peatlands is considered far more damaging to the climate per hectare than deforestation of tropical rainforests.\n\nReason (R): Tropical peatlands store carbon accumulated over millennia in their deep soil layers — a depth of 5–10 metres is common — whereas rainforest carbon is largely stored in aboveground biomass which reaccumulates over decades if the forest regrows.",
            "options": {
                "A": "Both A and R are true, and R is the correct explanation of A",
                "B": "Both A and R are true, but R is NOT the correct explanation of A",
                "C": "A is true but R is false",
                "D": "A is false but R is true"
            },
            "correct": "A",
            "q_num": "Q319"
        },
        {
            "test_id": 8, # Batch 7
            "topic_id": 4,
            "text": "Consider the following statements about the Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act and environmental issues:\n\nAssertion (A): Displacement of forest-dwelling communities from Protected Areas for conservation purposes without due process can attract provisions of the SC/ST (Prevention of Atrocities) Act, 1989.\n\nReason (R): Forcible dispossession of a tribal person from their land is listed as an offence under the SC/ST (PoA) Act, 1989 as amended in 2015, making conservation-related displacement legally accountable beyond just the Forest Rights Act framework.",
            "options": {
                "A": "Both A and R are true, and R is the correct explanation of A",
                "B": "Both A and R are true, but R is NOT the correct explanation of A",
                "C": "A is true but R is false",
                "D": "A is false but R is true"
            },
            "correct": "A",
            "q_num": "Q326"
        },
        {
            "test_id": 9, # Batch 8
            "topic_id": 4,
            "text": "Consider the following statements about the Miyawaki forest planting technique and urban biodiversity:\n\nAssertion (A): Miyawaki forests planted in Indian cities have been shown to support greater bird and butterfly diversity than conventional monoculture plantations of similar size.\n\nReason (R): The Miyawaki technique uses dense planting of multiple native species in a layered structure (shrub, sub-tree, tree, canopy), which creates complex habitat structure that supports greater species diversity than monoculture plantations.",
            "options": {
                "A": "Both A and R are true, and R is the correct explanation of A",
                "B": "Both A and R are true, but R is NOT the correct explanation of A",
                "C": "A is true but R is false",
                "D": "A is false but R is true"
            },
            "correct": "A",
            "q_num": "Q370"
        },
        {
            "test_id": 9, # Batch 8
            "topic_id": 4,
            "text": "Consider the following statements about the Sundarbans and climate adaptation:\n\nAssertion (A): The Sundarbans ecosystem provides one of the best natural examples of climate change adaptation through the combined effects of tidal flushing, mangrove sediment trapping and root system stabilization of coastlines.\n\nReason (R): Mangroves are among the most carbon-dense ecosystems on Earth, sequestering carbon at rates much higher per unit area than terrestrial forests, which makes them valuable for climate mitigation in addition to their adaptation role.",
            "options": {
                "A": "Both A and R are true, and R is the correct explanation of A",
                "B": "Both A and R are true, but R is NOT the correct explanation of A",
                "C": "A is true but R is false",
                "D": "A is false but R is true"
            },
            "correct": "B",
            "q_num": "Q384"
        },
        {
            "test_id": 6, # Batch 5
            "topic_id": 4,
            "text": "Consider the following statements about India's performance in international environmental indices:\n\n1. India ranked 180th out of 180 countries in the Environmental Performance Index (EPI) 2022, released by Yale and Columbia Universities.\n2. The EPI 2022 ranked India last primarily due to poor performance on air quality (PM2.5 exposure) and GHG emission growth rate indicators.\n3. India strongly rejected the EPI 2022 rankings, contending that the methodology was flawed and did not account for per capita emissions or India's climate actions.\n4. The EPI is a composite index covering 40 performance indicators across 11 issue categories including ecosystem vitality, climate change, air quality, water and sanitation, and biodiversity.\n\nWhich of the statements given above are correct?",
            "options": {
                "A": "1, 2 and 4 only",
                "B": "2, 3 and 4 only",
                "C": "1, 3 and 4 only",
                "D": "1, 2, 3 and 4"
            },
            "correct": "D",
            "q_num": "Q250"
        },
        {
            "test_id": 9, # Batch 8
            "topic_id": 4,
            "text": "Consider the following statements about India's climate policy narrative:\n\n1. India is the only G20 nation on track to achieve its climate targets under the Paris Agreement (though some trackers debate the 'only' part, India's official stance is consistent on this achievement).\n2. India's Long-Term Low-Emission Development Strategy (LT-LEDS) submitted to the UNFCCC emphasizes 'Lifestyle for Environment' (LiFE) as a key pillar of its climate action.\n3. India has achieved its target of 40% non-fossil fuel installed electricity capacity nine years ahead of the 2030 schedule.\n4. India's per capita GHG emissions are significantly lower than the global average, being approximately 2 tonnes CO2 equivalent compared to the global average of about 4.7 tonnes.\n\nWhich of the statements given above are correct?",
            "options": {
                "A": "1, 2 and 3 only",
                "B": "2, 3 and 4 only",
                "C": "1, 2 and 4 only",
                "D": "1, 2, 3 and 4"
            },
            "correct": "D",
            "q_num": "Q400"
        }
    ]
    
    for q_data in questions_to_add:
        # CLEANUP: Remove any existing broken record for this question number in this test
        db.execute(text("DELETE FROM questions WHERE test_id = :tid AND text_en LIKE :pattern"), 
                  {"tid": q_data["test_id"], "pattern": f"%{q_data['q_num']}%"})
        
        full_text = f"{q_data['q_num']}. {q_data['text']}"
        
        question = Question(
            test_id=q_data["test_id"],
            topic_id=q_data["topic_id"],
            text_en=full_text,
            options_en=q_data["options"],
            correct_option=q_data["correct"],
            explanation_en="Manual structural correction for Assertion-Reason format.",
            source="Manual Recovery",
            question_number=int(q_data["q_num"][1:]) # Strip 'Q'
        )
        db.add(question)
        print(f"Forced update of {q_data['q_num']} in Test {q_data['test_id']}")
    
    db.commit()
    db.close()

if __name__ == "__main__":
    insert_manual_questions()
