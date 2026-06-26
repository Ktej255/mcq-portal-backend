"""
Email templates for the Sarit Classes welcome sequence.
Each function returns a (subject, html_body) tuple.
"""

BRAND_COLOR = "#1d9e75"
BUTTON_STYLE = (
    "display: inline-block; padding: 14px 28px; "
    f"background-color: {BRAND_COLOR}; color: #ffffff; "
    "text-decoration: none; border-radius: 6px; font-weight: 600; "
    "font-size: 16px;"
)
BASE_URL = "https://saritclasses.com"


def _wrap_html(body_content: str) -> str:
    """Wrap email body in a responsive HTML shell with Sarit branding."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sarit Classes</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f4f7f6; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f4f7f6;">
        <tr>
            <td align="center" style="padding: 40px 20px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width: 600px; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.06);">
                    <!-- Header -->
                    <tr>
                        <td style="background-color: {BRAND_COLOR}; padding: 24px 32px; text-align: center;">
                            <h1 style="margin: 0; color: #ffffff; font-size: 22px; font-weight: 700; letter-spacing: -0.3px;">Sarit Classes</h1>
                        </td>
                    </tr>
                    <!-- Body -->
                    <tr>
                        <td style="padding: 32px;">
                            {body_content}
                        </td>
                    </tr>
                    <!-- Footer -->
                    <tr>
                        <td style="padding: 20px 32px; background-color: #f9fafb; border-top: 1px solid #e5e7eb; text-align: center;">
                            <p style="margin: 0 0 8px 0; color: #6b7280; font-size: 13px;">
                                Sarit Classes &mdash; UPSC Preparation, Reimagined
                            </p>
                            <p style="margin: 0; color: #9ca3af; font-size: 12px;">
                                You received this email because you signed up at saritclasses.com.<br>
                                To unsubscribe, reply to this email with "unsubscribe" or update your preferences in your account settings.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""


def welcome_email(name: str, first_topic: str = "Plate Tectonics") -> tuple[str, str]:
    """Day 0: Welcome email sent immediately after signup."""
    subject = f"Welcome to Sarit Classes, {name}! Your study plan is ready"
    body = f"""
        <h2 style="margin: 0 0 16px 0; color: #111827; font-size: 20px;">Welcome aboard, {name}! 🎯</h2>
        <p style="color: #374151; font-size: 15px; line-height: 1.6; margin: 0 0 16px 0;">
            You just took the most important step in your UPSC journey &mdash; committing to a structured, adaptive study plan that meets you where you are.
        </p>
        <p style="color: #374151; font-size: 15px; line-height: 1.6; margin: 0 0 16px 0;">
            Here's what we've set up for you:
        </p>
        <ul style="color: #374151; font-size: 15px; line-height: 1.8; margin: 0 0 24px 0; padding-left: 20px;">
            <li><strong>Personalized study plan</strong> based on your goals and timeline</li>
            <li><strong>Daily learning loops</strong> with spaced repetition built in</li>
            <li><strong>Gap reports</strong> that show exactly where to focus</li>
            <li><strong>Your first topic:</strong> {first_topic}</li>
        </ul>
        <p style="color: #374151; font-size: 15px; line-height: 1.6; margin: 0 0 24px 0;">
            Ready to dive in? Your first topic is waiting:
        </p>
        <p style="text-align: center; margin: 0 0 24px 0;">
            <a href="{BASE_URL}/upsc/geography/lms" style="{BUTTON_STYLE}">
                Start Your First Topic
            </a>
        </p>
        <p style="color: #6b7280; font-size: 14px; line-height: 1.5; margin: 0;">
            Over the next two weeks, we'll send you a few emails to help you get the most out of Sarit Classes. Every message is designed to help, never to spam.
        </p>
    """
    return subject, _wrap_html(body)


def daily_loop_email(name: str) -> tuple[str, str]:
    """Day 2: How the daily loop works."""
    subject = f"{name}, here's how your daily learning loop works"
    body = f"""
        <h2 style="margin: 0 0 16px 0; color: #111827; font-size: 20px;">Your Daily Loop, Explained 🔄</h2>
        <p style="color: #374151; font-size: 15px; line-height: 1.6; margin: 0 0 16px 0;">
            Hey {name}, now that you've had a day to explore, let's talk about the engine behind your progress: the <strong>Daily Learning Loop</strong>.
        </p>
        <p style="color: #374151; font-size: 15px; line-height: 1.6; margin: 0 0 16px 0;">
            Each day, Sarit prepares a focused session for you with three components:
        </p>
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin: 0 0 24px 0;">
            <tr>
                <td style="padding: 12px 16px; background-color: #ecfdf5; border-radius: 8px; margin-bottom: 8px;">
                    <p style="margin: 0 0 4px 0; font-weight: 600; color: {BRAND_COLOR}; font-size: 14px;">1. Learn</p>
                    <p style="margin: 0; color: #374151; font-size: 14px;">A new concept or subtopic, delivered as a concise lesson with key takeaways.</p>
                </td>
            </tr>
            <tr><td style="height: 8px;"></td></tr>
            <tr>
                <td style="padding: 12px 16px; background-color: #ecfdf5; border-radius: 8px;">
                    <p style="margin: 0 0 4px 0; font-weight: 600; color: {BRAND_COLOR}; font-size: 14px;">2. Practice</p>
                    <p style="margin: 0; color: #374151; font-size: 14px;">MCQs that test understanding, not just recall. Each wrong answer reveals a learning gap.</p>
                </td>
            </tr>
            <tr><td style="height: 8px;"></td></tr>
            <tr>
                <td style="padding: 12px 16px; background-color: #ecfdf5; border-radius: 8px;">
                    <p style="margin: 0 0 4px 0; font-weight: 600; color: {BRAND_COLOR}; font-size: 14px;">3. Revisit</p>
                    <p style="margin: 0; color: #374151; font-size: 14px;">Spaced repetition brings back concepts just before you'd forget them.</p>
                </td>
            </tr>
        </table>
        <p style="color: #374151; font-size: 15px; line-height: 1.6; margin: 0 0 24px 0;">
            The best part? You don't have to plan anything. Just show up and the system adapts to your pace.
        </p>
        <p style="text-align: center; margin: 0 0 24px 0;">
            <a href="{BASE_URL}/upsc/geography/lms" style="{BUTTON_STYLE}">
                Continue Today's Loop
            </a>
        </p>
        <p style="color: #6b7280; font-size: 14px; line-height: 1.5; margin: 0;">
            Consistency beats intensity. Even 20 minutes a day compounds into serious progress.
        </p>
    """
    return subject, _wrap_html(body)


def first_gap_report_email(name: str) -> tuple[str, str]:
    """Day 4: Your first gap report is ready."""
    subject = f"{name}, your first gap report is ready 📊"
    body = f"""
        <h2 style="margin: 0 0 16px 0; color: #111827; font-size: 20px;">Your First Gap Report 📊</h2>
        <p style="color: #374151; font-size: 15px; line-height: 1.6; margin: 0 0 16px 0;">
            Hey {name}, after a few days of practice, we've mapped your knowledge landscape. Your <strong>Gap Report</strong> is now live.
        </p>
        <p style="color: #374151; font-size: 15px; line-height: 1.6; margin: 0 0 16px 0;">
            Here's what it tells you:
        </p>
        <ul style="color: #374151; font-size: 15px; line-height: 1.8; margin: 0 0 24px 0; padding-left: 20px;">
            <li><strong>Strong areas</strong> &mdash; concepts you've nailed and can revise less often</li>
            <li><strong>Weak spots</strong> &mdash; topics that need more attention in upcoming loops</li>
            <li><strong>Blind spots</strong> &mdash; areas you haven't touched yet but are important for the syllabus</li>
        </ul>
        <p style="color: #374151; font-size: 15px; line-height: 1.6; margin: 0 0 24px 0;">
            This isn't a judgment &mdash; it's a compass. The system will automatically prioritize your weak spots in upcoming sessions, but you can also explore the report yourself.
        </p>
        <p style="text-align: center; margin: 0 0 24px 0;">
            <a href="{BASE_URL}/upsc/dashboard" style="{BUTTON_STYLE}">
                View Your Gap Report
            </a>
        </p>
        <p style="color: #6b7280; font-size: 14px; line-height: 1.5; margin: 0;">
            The more you practice, the sharper this report gets. Keep going!
        </p>
    """
    return subject, _wrap_html(body)


def week_one_retro_email(name: str) -> tuple[str, str]:
    """Day 7: Week 1 retrospective."""
    subject = f"Week 1 done, {name}! Here's your progress snapshot 🏆"
    body = f"""
        <h2 style="margin: 0 0 16px 0; color: #111827; font-size: 20px;">Week 1 Retrospective 🏆</h2>
        <p style="color: #374151; font-size: 15px; line-height: 1.6; margin: 0 0 16px 0;">
            {name}, you've completed your first full week with Sarit Classes. That's a real milestone &mdash; most aspirants never make it past day 3 of a new study system.
        </p>
        <p style="color: #374151; font-size: 15px; line-height: 1.6; margin: 0 0 16px 0;">
            Here's what a week of structured learning looks like:
        </p>
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin: 0 0 24px 0; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden;">
            <tr style="background-color: #f9fafb;">
                <td style="padding: 12px 16px; border-bottom: 1px solid #e5e7eb;">
                    <span style="color: #6b7280; font-size: 13px;">Topics Covered</span><br>
                    <span style="color: #111827; font-size: 18px; font-weight: 600;">Multiple subtopics explored</span>
                </td>
            </tr>
            <tr>
                <td style="padding: 12px 16px; border-bottom: 1px solid #e5e7eb;">
                    <span style="color: #6b7280; font-size: 13px;">Practice Questions Attempted</span><br>
                    <span style="color: #111827; font-size: 18px; font-weight: 600;">Steadily building</span>
                </td>
            </tr>
            <tr style="background-color: #f9fafb;">
                <td style="padding: 12px 16px;">
                    <span style="color: #6b7280; font-size: 13px;">Knowledge Gaps Identified</span><br>
                    <span style="color: #111827; font-size: 18px; font-weight: 600;">Being addressed automatically</span>
                </td>
            </tr>
        </table>
        <p style="color: #374151; font-size: 15px; line-height: 1.6; margin: 0 0 24px 0;">
            The compound effect is real. Each day you show up, your understanding deepens and retention strengthens. Keep this rhythm going into week 2.
        </p>
        <p style="text-align: center; margin: 0 0 24px 0;">
            <a href="{BASE_URL}/upsc/dashboard" style="{BUTTON_STYLE}">
                See Your Full Progress
            </a>
        </p>
        <p style="color: #6b7280; font-size: 14px; line-height: 1.5; margin: 0;">
            Fun fact: Students who complete week 2 are 4x more likely to maintain a consistent study habit through their entire prep.
        </p>
    """
    return subject, _wrap_html(body)


def upgrade_nudge_email(name: str) -> tuple[str, str]:
    """Day 14: Unlock deeper features."""
    subject = f"{name}, ready to unlock the full Sarit experience?"
    body = f"""
        <h2 style="margin: 0 0 16px 0; color: #111827; font-size: 20px;">Two Weeks In &mdash; What's Next? 🚀</h2>
        <p style="color: #374151; font-size: 15px; line-height: 1.6; margin: 0 0 16px 0;">
            {name}, you've been at this for two weeks now, and that consistency is impressive. You've built a real study habit.
        </p>
        <p style="color: #374151; font-size: 15px; line-height: 1.6; margin: 0 0 16px 0;">
            Here's what's available when you're ready to go deeper:
        </p>
        <ul style="color: #374151; font-size: 15px; line-height: 1.8; margin: 0 0 24px 0; padding-left: 20px;">
            <li><strong>Full syllabus coverage</strong> &mdash; all GS papers, not just Geography</li>
            <li><strong>Mains answer writing</strong> &mdash; AI-evaluated practice with PYQ patterns</li>
            <li><strong>Advanced gap analytics</strong> &mdash; deeper insights into cognitive patterns</li>
            <li><strong>Optional subject modules</strong> &mdash; structured prep for your chosen optional</li>
            <li><strong>Weekly retros with AI coaching</strong> &mdash; personalized strategy adjustments</li>
        </ul>
        <p style="color: #374151; font-size: 15px; line-height: 1.6; margin: 0 0 24px 0;">
            No pressure &mdash; your current plan is already powerful. But if you want to accelerate, we've built the tools for serious aspirants like you.
        </p>
        <p style="text-align: center; margin: 0 0 24px 0;">
            <a href="{BASE_URL}/upsc/pricing" style="{BUTTON_STYLE}">
                Explore Full Access
            </a>
        </p>
        <p style="color: #6b7280; font-size: 14px; line-height: 1.5; margin: 0;">
            Questions? Just reply to this email. We read every response.
        </p>
    """
    return subject, _wrap_html(body)
