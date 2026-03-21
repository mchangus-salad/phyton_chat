import uuid

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from api.models import Subscription, SubscriptionPlan, Tenant, TenantMembership


def run_demo():
    user_model = get_user_model()
    suffix = uuid.uuid4().hex[:8]

    username = f"demo_chat_{suffix}"
    password = "DemoChat123!"

    user = user_model.objects.create_user(username=username, password=password)
    tenant = Tenant.objects.create(name=f"Demo Tenant {suffix}", tenant_type="clinic", owner=user)
    TenantMembership.objects.create(
        tenant=tenant,
        user=user,
        role=TenantMembership.Role.CLINICIAN,
        is_active=True,
    )

    plan = SubscriptionPlan.objects.create(
        code=f"demo-chat-plan-{suffix}",
        name="Demo Chat Plan",
        description="Demo plan for chat flow",
        billing_cycle=SubscriptionPlan.BillingCycle.MONTHLY,
        price_cents=1000,
        billing_model="hybrid",
        currency="USD",
        max_monthly_requests=1000,
        max_users=10,
        seat_price_cents=100,
        api_overage_per_1000_cents=10,
    )
    Subscription.objects.create(tenant=tenant, plan=plan, status=Subscription.Status.ACTIVE, provider="internal")

    client = APIClient()

    token_resp = client.post(
        "/api/v1/auth/token/",
        {"username": username, "password": password},
        format="json",
    )
    access_token = token_resp.data["access"]

    auth_headers = {
        "HTTP_AUTHORIZATION": f"Bearer {access_token}",
        "HTTP_X_TENANT_ID": str(tenant.tenant_id),
    }

    chat_resp = client.post("/api/v1/agent/chats/", {"title": ""}, format="json", **auth_headers)
    session_id = str(chat_resp.data["session_id"])

    user_msg = client.post(
        f"/api/v1/agent/chats/{session_id}/messages/",
        {"role": "user", "content": "Summarize heart failure treatment updates."},
        format="json",
        **auth_headers,
    )

    assistant_text = "Guideline update: prioritize SGLT2 inhibitors in eligible HFrEF patients."
    assistant_msg = client.post(
        f"/api/v1/agent/chats/{session_id}/messages/",
        {"role": "assistant", "content": assistant_text},
        format="json",
        **auth_headers,
    )

    start_offset = assistant_text.index("SGLT2")
    end_offset = start_offset + len("SGLT2 inhibitors")

    highlight_resp = client.post(
        f"/api/v1/agent/chats/{session_id}/highlights/",
        {
            "message_id": assistant_msg.data["message_id"],
            "selected_text": "SGLT2 inhibitors",
            "start_offset": start_offset,
            "end_offset": end_offset,
        },
        format="json",
        **auth_headers,
    )

    detail_resp = client.get(
        f"/api/v1/agent/chats/{session_id}/?message_limit=2&message_offset=0&from_end=1",
        format="json",
        **auth_headers,
    )

    search_resp = client.get(
        "/api/v1/agent/chats/?q=SGLT2&limit=5&offset=0",
        format="json",
        **auth_headers,
    )

    pop_resp = client.delete(
        f"/api/v1/agent/chats/{session_id}/highlights/pop/",
        format="json",
        **auth_headers,
    )

    detail_after_pop = client.get(
        f"/api/v1/agent/chats/{session_id}/",
        format="json",
        **auth_headers,
    )

    print("DEMO_RESULTS")
    print(f"token_status={token_resp.status_code}")
    print(f"chat_create_status={chat_resp.status_code} session_id={session_id}")
    print(f"user_message_status={user_msg.status_code} id={user_msg.data.get('message_id')}")
    print(f"assistant_message_status={assistant_msg.status_code} id={assistant_msg.data.get('message_id')}")
    print(f"auto_title={detail_resp.data.get('title')}")
    print(f"highlight_create_status={highlight_resp.status_code} highlight_id={highlight_resp.data.get('highlight_id')}")
    print(f"detail_status={detail_resp.status_code} messages={len(detail_resp.data.get('messages', []))} highlights={len(detail_resp.data.get('highlights', []))}")
    print(f"search_status={search_resp.status_code} returned={len(search_resp.data.get('items', []))} has_more={search_resp.data.get('pagination', {}).get('has_more')}")
    print(f"highlight_pop_status={pop_resp.status_code} undone_id={pop_resp.data.get('undone_highlight_id')}")
    print(f"detail_after_pop_status={detail_after_pop.status_code} highlights={len(detail_after_pop.data.get('highlights', []))}")


run_demo()
