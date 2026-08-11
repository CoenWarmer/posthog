from posthog.test.base import BaseTest
from unittest.mock import patch

from django.apps import apps
from django.test import Client

from parameterized import parameterized

from posthog.models.comment import Comment
from posthog.models.organization import OrganizationMembership
from posthog.models.user import User

from products.conversations.backend.models import (
    EMAIL_THREAD_COMMENT_SCOPE,
    EmailChannel,
    EmailChannelKind,
    EmailOutboxMessage,
    EmailThread,
    EmailThreadAccess,
    EmailThreadAccountLink,
    EmailThreadMessage,
    EmailThreadMessageDirection,
    EmailThreadParticipant,
    EmailThreadParticipantKind,
    Ticket,
)


class TestCustomerEmailIngestion(BaseTest):
    def setUp(self) -> None:
        super().setUp()
        self.client = Client()
        self.channel = EmailChannel.objects.create(
            team=self.team,
            kind=EmailChannelKind.CUSTOMER_COMMUNICATION,
            owner=self.user,
            inbound_token="c0570a111",
            from_email="csm@example.com",
            from_name="Customer success",
            domain="example.com",
            domain_verified=True,
        )
        signature_patcher = patch(
            "products.conversations.backend.api.email_events.validate_webhook_signature",
            return_value=True,
        )
        signature_patcher.start()
        self.addCleanup(signature_patcher.stop)

    def _post_email(
        self,
        *,
        message_id: str,
        recipient: str = "team-c0570a111@mg.posthog.com",
        **overrides: str,
    ):
        data = {
            "token": "webhook-token",
            "timestamp": "1749565800",
            "signature": "webhook-signature",
            "recipient": recipient,
            "from": "Example customer <customer@customer.example>",
            "sender": "customer@customer.example",
            "To": "CSM <csm@example.com>",
            "Message-Id": message_id,
            "Date": "Tue, 10 Jun 2025 14:30:00 +0000",
            "subject": "Account question",
            "stripped-text": "Can you help?",
            "body-plain": "Can you help?",
        }
        data.update(overrides)
        return self.client.post("/api/conversations/v1/email/inbound", data)

    def _post_outbound_email(
        self,
        *,
        message_id: str,
        **overrides: str,
    ):
        data = {
            "token": "webhook-token",
            "timestamp": "1749565800",
            "signature": "webhook-signature",
            "recipient": "sent@mg.posthog.com",
            "from": "Customer success <csm@example.com>",
            "sender": "csm@example.com",
            "To": "Prospect <prospect@future.example>",
            "Message-Id": message_id,
            "Date": "Tue, 10 Jun 2025 14:00:00 +0000",
            "subject": "Account update",
            "stripped-text": "Here is your account update.",
            "body-plain": "Here is your account update.",
            "X-Mailgun-Spf": "pass",
        }
        data.update(overrides)
        return self.client.post("/api/conversations/v1/email/outbound", data)

    def test_forwarding_verification_is_visible_only_to_channel_owner_without_support_side_effects(self) -> None:
        colleague = User.objects.create(email="colleague@example.com", current_team=self.team)
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=colleague,
            level=OrganizationMembership.Level.MEMBER,
        )

        response = self._post_email(
            message_id="<forwarding-confirmation@gmail.com>",
            **{
                "from": "Gmail forwarding <forwarding-noreply@google.com>",
                "sender": "forwarding-noreply@google.com",
                "To": "CSM <csm@example.com>, Colleague <colleague@example.com>",
                "subject": "Gmail forwarding confirmation",
                "body-plain": "Use confirmation code 123456 to finish forwarding setup.",
                "stripped-text": "Use confirmation code 123456 to finish forwarding setup.",
            },
        )

        assert response.status_code == 200
        thread = EmailThread.objects.for_team(self.team.id).get()
        message = EmailThreadMessage.objects.for_team(self.team.id).select_related("comment").get()
        assert thread.subject == "Gmail forwarding confirmation"
        assert thread.message_count == 1
        assert thread.first_message_at is not None
        assert thread.first_message_at.isoformat() == "2025-06-10T14:30:00+00:00"
        assert thread.last_message_at == thread.first_message_at
        assert thread.preview == "Use confirmation code 123456 to finish forwarding setup."
        assert message.comment.scope == EMAIL_THREAD_COMMENT_SCOPE
        assert message.comment.item_id == str(thread.id)
        assert message.comment.content == "Use confirmation code 123456 to finish forwarding setup."
        assert message.sent_at == thread.first_message_at
        assert message.sender_email == "forwarding-noreply@google.com"
        assert message.sender_authenticated is False
        assert message.to_recipients == [
            {"name": "CSM", "email": "csm@example.com"},
            {"name": "Colleague", "email": "colleague@example.com"},
        ]
        participants = {
            participant.email: participant.kind
            for participant in EmailThreadParticipant.objects.for_team(self.team.id).filter(thread=thread)
        }
        assert participants == {
            "colleague@example.com": EmailThreadParticipantKind.INTERNAL.value,
            "csm@example.com": EmailThreadParticipantKind.INTERNAL.value,
            "forwarding-noreply@google.com": EmailThreadParticipantKind.CUSTOMER.value,
            self.user.email: EmailThreadParticipantKind.INTERNAL.value,
        }
        assert EmailThreadAccess.objects.for_team(self.team.id).filter(thread=thread, user=self.user).exists()
        assert not Ticket.objects.filter(team=self.team).exists()
        assert not EmailOutboxMessage.objects.filter(team=self.team).exists()

        self.client.force_login(self.user)
        list_response = self.client.get("/api/conversations/v1/email/threads")
        detail_response = self.client.get(f"/api/conversations/v1/email/threads/{thread.id}")
        assert list_response.status_code == 200
        assert list_response.json()["count"] == 1
        assert list_response.json()["results"][0]["subject"] == "Gmail forwarding confirmation"
        assert detail_response.status_code == 200
        assert detail_response.json()["messages"][0]["content"] == (
            "Use confirmation code 123456 to finish forwarding setup."
        )

        self.client.force_login(colleague)
        other_list_response = self.client.get("/api/conversations/v1/email/threads")
        other_detail_response = self.client.get(f"/api/conversations/v1/email/threads/{thread.id}")
        assert other_list_response.status_code == 200
        assert other_list_response.json() == {"count": 0, "results": []}
        assert other_detail_response.status_code == 404

    @parameterized.expand(["in_reply_to", "references"])
    def test_rfc_reply_headers_continue_the_existing_thread(self, header_kind: str) -> None:
        root_message_id = f"<root-{header_kind}@customer.example>"
        root_response = self._post_email(
            message_id=root_message_id,
            **{
                "X-Mailgun-Spf": "pass",
                "body-plain": "Initial message with forwarded context",
                "stripped-text": "Initial message",
            },
        )
        reply_fields = {
            "Date": "Tue, 10 Jun 2025 15:30:00 +0000",
            "body-plain": "Reply only\n\nOn Tuesday, Customer success wrote:\n> Initial message",
            "stripped-text": "Reply only",
        }
        if header_kind == "in_reply_to":
            reply_fields["In-Reply-To"] = root_message_id
        else:
            reply_fields["References"] = f"<older@customer.example> {root_message_id}"

        reply_response = self._post_email(
            message_id=f"<reply-{header_kind}@customer.example>",
            **reply_fields,
        )

        assert root_response.status_code == 200
        assert reply_response.status_code == 200
        thread = EmailThread.objects.for_team(self.team.id).get()
        messages = list(
            EmailThreadMessage.objects.for_team(self.team.id).filter(thread=thread).select_related("comment")
        )
        assert thread.message_count == 2
        assert thread.preview == "Reply only"
        assert len(messages) == 2
        assert messages[0].sender_authenticated is True
        assert messages[0].comment.content == "Initial message with forwarded context"
        assert messages[1].comment.content == "Reply only"
        assert messages[1].in_reply_to == (root_message_id if header_kind == "in_reply_to" else None)
        assert messages[1].references == (
            [] if header_kind == "in_reply_to" else ["<older@customer.example>", root_message_id]
        )

    def test_forwarded_message_links_to_matching_customer_account(self) -> None:
        account_model = apps.get_model("customer_analytics", "Account")
        account = account_model.objects.for_team(self.team.id).create(
            team=self.team,
            name="Customer account",
            external_id="customer-account",
            _properties={"email_domains": ["customer.example"]},
        )

        response = self._post_email(message_id="<linked@customer.example>")

        assert response.status_code == 200
        link = EmailThreadAccountLink.objects.for_team(self.team.id).get()
        assert link.account_id == str(account.id)
        assert link.account_external_id == "customer-account"
        assert link.match_source == "email_domain"

    def test_outbound_message_is_recovered_when_a_later_reply_matches_an_account(self) -> None:
        outbound_message_id = "<outbound@customer-success.example>"
        outbound_response = self._post_outbound_email(message_id=outbound_message_id)

        assert outbound_response.status_code == 200
        thread = EmailThread.objects.for_team(self.team.id).get()
        assert not EmailThreadAccountLink.objects.for_team(self.team.id).filter(thread=thread).exists()

        account_model = apps.get_model("customer_analytics", "Account")
        account = account_model.objects.for_team(self.team.id).create(
            team=self.team,
            name="Future account",
            external_id="future-account",
            _properties={"known_emails": ["prospect@future.example"]},
        )
        reply_response = self._post_email(
            message_id="<reply@future.example>",
            **{
                "from": "Prospect <prospect@future.example>",
                "sender": "prospect@future.example",
                "To": "Customer success <csm@example.com>",
                "In-Reply-To": outbound_message_id,
                "Date": "Tue, 10 Jun 2025 15:00:00 +0000",
                "body-plain": "Thanks for the update.",
                "stripped-text": "Thanks for the update.",
                "X-Mailgun-Spf": "pass",
            },
        )

        assert reply_response.status_code == 200
        thread.refresh_from_db()
        messages = list(EmailThreadMessage.objects.for_team(self.team.id).filter(thread=thread))
        assert thread.message_count == 2
        assert [message.direction for message in messages] == [
            EmailThreadMessageDirection.OUTBOUND,
            EmailThreadMessageDirection.INBOUND,
        ]
        assert messages[0].sender_email == "csm@example.com"
        assert messages[0].sender_authenticated is True
        assert messages[1].in_reply_to == outbound_message_id
        link = EmailThreadAccountLink.objects.for_team(self.team.id).get(thread=thread)
        assert link.account_id == str(account.id)
        assert EmailThreadAccess.objects.for_team(self.team.id).filter(thread=thread, user=self.user).exists()
        assert not Ticket.objects.filter(team=self.team).exists()
        assert not EmailOutboxMessage.objects.filter(team=self.team).exists()

    def test_outbound_capture_rejects_a_sender_with_a_different_envelope_address(self) -> None:
        response = self._post_outbound_email(
            message_id="<spoofed@customer-success.example>",
            sender="attacker@example.com",
        )

        assert response.status_code == 200
        assert not EmailThread.objects.for_team(self.team.id).exists()

    def test_outbound_capture_drops_internal_only_messages(self) -> None:
        colleague = User.objects.create(email="colleague@example.com", current_team=self.team)
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=colleague,
            level=OrganizationMembership.Level.MEMBER,
        )

        response = self._post_outbound_email(
            message_id="<internal@example.com>",
            To="Colleague <colleague@example.com>",
        )

        assert response.status_code == 200
        assert not EmailThread.objects.for_team(self.team.id).exists()

    def test_duplicate_delivery_creates_one_message_and_grants_each_channel_owner_access(self) -> None:
        message_id = "<duplicate@customer.example>"
        first_response = self._post_email(message_id=message_id)
        retry_response = self._post_email(message_id=message_id)

        second_owner = User.objects.create(email="second-csm@example.com", current_team=self.team)
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=second_owner,
            level=OrganizationMembership.Level.MEMBER,
        )
        EmailChannel.objects.create(
            team=self.team,
            kind=EmailChannelKind.CUSTOMER_COMMUNICATION,
            owner=second_owner,
            inbound_token="5ec00dc5a",
            from_email=second_owner.email,
            from_name="Second CSM",
            domain="example.com",
            domain_verified=True,
        )
        second_owner_response = self._post_email(
            message_id=message_id,
            recipient="team-5ec00dc5a@mg.posthog.com",
        )

        assert first_response.status_code == 200
        assert retry_response.status_code == 200
        assert second_owner_response.status_code == 200
        thread = EmailThread.objects.for_team(self.team.id).get()
        assert thread.message_count == 1
        assert EmailThreadMessage.objects.for_team(self.team.id).filter(thread=thread).count() == 1
        assert (
            Comment.objects.filter(team=self.team, scope=EMAIL_THREAD_COMMENT_SCOPE, item_id=str(thread.id)).count()
            == 1
        )
        assert set(
            EmailThreadAccess.objects.for_team(self.team.id).filter(thread=thread).values_list("user_id", flat=True)
        ) == {self.user.id, second_owner.id}
