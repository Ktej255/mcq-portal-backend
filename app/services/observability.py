from typing import Dict, Any
from sqlalchemy.orm import Session
from app.models.domain import Report, ExamEvent, User, LearningIntervention, Question, Attempt, AttemptStatusEnum
from app.services.content_intelligence_engine import content_observability
from app.services.educational_memory_engine import educational_memory_observability
from app.services.intervention_analytics import longitudinal_intervention_analytics
from app.services.knowledge_graph_engine import build_knowledge_graph, graph_observability
from app.services.educational_orchestrator import orchestration_observability
from app.services.session_intelligence_engine import build_session_intelligence, educator_live_awareness
from app.services.telemetry_reconstruction import reconstruct_attempt_timeline
import time

class ObservabilityService:
    def get_pipeline_health(self, db: Session) -> Dict[str, Any]:
        """
        Calculates health metrics for the cognitive pipeline.
        """
        # 1. Pipeline Status
        total_reports = db.query(Report).count()
        pending = db.query(Report).filter(Report.processing_status == "PENDING").count()
        failed = db.query(Report).filter(Report.processing_status == "FAILED").count()
        
        # 2. Narrative Quality Drift
        # Average hallucination score (from evaluation_metadata)
        # Note: This requires complex JSON query in SQL, simplified here
        reports_with_eval = db.query(Report).filter(Report.evaluation_metadata != None).limit(100).all()
        recent_events = db.query(ExamEvent).order_by(ExamEvent.timestamp.desc()).limit(500).all()
        users_with_adaptive_profiles = db.query(User).filter(User.behavioral_profile != None).limit(100).all()
        recent_interventions = db.query(LearningIntervention).limit(500).all()
        
        avg_hallucination = 0
        avg_uncertainty = 0
        human_review_required = 0
        if reports_with_eval:
            avg_hallucination = sum([r.evaluation_metadata.get('hallucination_score', 0) for r in reports_with_eval]) / len(reports_with_eval)
            avg_uncertainty = sum([r.evaluation_metadata.get('uncertainty_score', 0) for r in reports_with_eval]) / len(reports_with_eval)
            human_review_required = len([r for r in reports_with_eval if r.evaluation_metadata.get('requires_human_review')])
        adaptive_profiles = [u.behavioral_profile for u in users_with_adaptive_profiles if isinstance(u.behavioral_profile, dict)]
        low_reliability_profiles = [
            profile for profile in adaptive_profiles
            if profile.get("longitudinal_reliability", {}).get("level") == "LOW"
        ]
        volatile_profiles = [
            profile for profile in adaptive_profiles
            if profile.get("behavioral_stability", {}).get("consistency_score", 1) < 0.45
        ]

        # 3. Event Ingestion Latency (Simplified)
        # We can check the gap between event timestamp and DB insertion
        telemetry_quality = reconstruct_attempt_timeline(list(reversed(recent_events)))["quality"] if recent_events else {}
        intervention_metrics = longitudinal_intervention_analytics(db) if recent_interventions else {}
        graph = build_knowledge_graph(db)
        graph_metrics = graph_observability(graph)
        recent_questions = db.query(Question).filter(Question.explanation_en != None).limit(500).all()
        explanation_resources = [
            {
                "id": f"question:{question.id}",
                "type": "MCQ_EXPLANATION",
                "text": question.explanation_en or question.text_en or "",
                "modalities": ["TEXT"],
            }
            for question in recent_questions
        ]
        content_metrics = content_observability(explanation_resources, graph) if explanation_resources else {}
        memory_metrics = educational_memory_observability(db)
        orchestration_metrics = orchestration_observability(db)
        active_attempts = db.query(Attempt).filter(Attempt.status == AttemptStatusEnum.IN_PROGRESS).limit(100).all()
        live_sessions = [build_session_intelligence(db, attempt.id) for attempt in active_attempts]
        live_awareness = educator_live_awareness(live_sessions)
        
        return {
            "pipeline": {
                "total_processed": total_reports,
                "pending_tasks": pending,
                "failure_rate": (failed / total_reports * 100) if total_reports > 0 else 0
            },
            "accuracy_drift": {
                "avg_hallucination_score": round(avg_hallucination, 2),
                "avg_uncertainty_score": round(avg_uncertainty, 2),
                "human_review_required_rate": round((human_review_required / len(reports_with_eval) * 100), 2) if reports_with_eval else 0,
                "quality_baseline_status": "STABLE" if avg_hallucination < 0.2 else "ATTENTION_REQUIRED"
            },
            "inference_reliability": {
                "reports_with_reliability_metadata": len(reports_with_eval),
                "unreliable_inference_rate": round((human_review_required / len(reports_with_eval) * 100), 2) if reports_with_eval else 0,
            },
            "telemetry": {
                "recent_event_count": len(recent_events),
                "heartbeat_density": telemetry_quality.get("heartbeat_density", 0),
                "continuity_score": telemetry_quality.get("continuity_score", 0),
                "focus_reliability": telemetry_quality.get("focus_reliability", 0),
                "idle_reliability": telemetry_quality.get("idle_reliability", 0),
                "temporal_coherence": telemetry_quality.get("temporal_coherence", 0),
            },
            "adaptive_intelligence": {
                "profile_count": len(adaptive_profiles),
                "low_reliability_rate": round((len(low_reliability_profiles) / len(adaptive_profiles) * 100), 2) if adaptive_profiles else 0,
                "high_volatility_profile_rate": round((len(volatile_profiles) / len(adaptive_profiles) * 100), 2) if adaptive_profiles else 0,
                "adaptation_stability_status": "CAUTIOUS" if low_reliability_profiles else "STABLE",
            },
            "experimentation": {
                "intervention_count": len(recent_interventions),
                "acceptance_rate": intervention_metrics.get("overall_acceptance", {}).get("accepted_rate", 0),
                "abandonment_rate": intervention_metrics.get("overall_acceptance", {}).get("abandonment_rate", 0),
                "unstable_outcome_rate": intervention_metrics.get("unstable_outcome_rate", 0),
                "strategy_count": len(intervention_metrics.get("strategy_results", {})),
            },
            "conceptual_intelligence": {
                "topic_count": graph.get("topic_count", 0),
                "edge_count": graph_metrics.get("coverage", {}).get("edge_count", 0),
                "dependency_coverage": graph_metrics.get("coverage", {}).get("dependency_coverage", 0),
                "unresolved_prerequisite_chain_count": len(graph_metrics.get("unresolved_prerequisite_chains", [])),
                "bottleneck_count": graph_metrics.get("bottleneck_count", 0),
                "bridge_count": graph_metrics.get("bridge_count", 0),
            },
            "content_intelligence": {
                "resource_count": content_metrics.get("resource_count", 0),
                "concept_coverage_rate": content_metrics.get("concept_coverage_rate", 0),
                "overloaded_content_count": content_metrics.get("overloaded_content_count", 0),
                "low_quality_explanation_cluster_count": content_metrics.get("low_quality_explanation_cluster_count", 0),
                "bottleneck_resource_gap_count": len(content_metrics.get("bottleneck_resource_gaps", [])) if content_metrics else 0,
            },
            "educational_memory": {
                "memory_profile_count": memory_metrics.get("memory_profile_count", 0),
                "misconception_persistence_rate": memory_metrics.get("misconception_persistence_rate", 0),
                "failed_recovery_count": memory_metrics.get("failed_recovery_count", 0),
                "recovery_durability_rate": memory_metrics.get("recovery_durability_rate", 0),
                "narrative_stability": memory_metrics.get("narrative_stability", 0),
            },
            "educational_orchestration": {
                "orchestrated_user_count": orchestration_metrics.get("orchestrated_user_count", 0),
                "arbitration_conflict_count": orchestration_metrics.get("arbitration_conflict_count", 0),
                "blocked_unsafe_adaptation_count": orchestration_metrics.get("blocked_unsafe_adaptation_count", 0),
                "human_review_escalation_rate": orchestration_metrics.get("human_review_escalation_rate", 0),
                "low_confidence_orchestration_rate": orchestration_metrics.get("low_confidence_orchestration_rate", 0),
            },
            "realtime_intelligence": {
                "active_session_count": live_awareness.get("active_session_count", 0),
                "unstable_session_count": live_awareness.get("unstable_session_count", 0),
                "high_overload_risk_count": live_awareness.get("high_overload_risk_count", 0),
                "telemetry_degradation_count": live_awareness.get("telemetry_degradation_count", 0),
                "educator_alert_count": len(live_awareness.get("educator_alerts", [])),
            },
            "system_load": {
                "active_ingestion_threads": 1, # Placeholder
                "queue_backlog_size": pending
            }
        }

observability_service = ObservabilityService()
