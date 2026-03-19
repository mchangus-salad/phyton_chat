from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class AgentAnonRateThrottle(AnonRateThrottle):
    scope = "agent_anon"


class AgentUserRateThrottle(UserRateThrottle):
    scope = "agent_user"
