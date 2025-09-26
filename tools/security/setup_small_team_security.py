"""
DinoAir Security Configuration Example for Small Teams

This shows how to set up relaxed security settings for a 2-person company.
"""

from utils.network_security import NetworkSecurityManager, create_small_team_security_config


def setup_small_team_security():
    """Set up security for a small team (you and your partner)."""

    # Create relaxed security configuration
    security_config = create_small_team_security_config()
    security_manager = NetworkSecurityManager(security_config)

    print("🚀 Small Team Security Configuration:")
    print("   • Rate Limit: 600 requests/minute per IP (10 per second)")
    print("   • Global Limit: 2000 requests/minute")
    print("   • HTTPS Required: No (can use HTTP for development)")
    print("   • DDoS Protection: 5 minute blocks (instead of hours)")
    print("   • CORS: Supports common dev ports (3000, 5173, 5174, 8000)")
    print("   • IP Restrictions: None (all IPs allowed)")

    return security_manager


def integrate_with_fastapi():
    """Show how to integrate with your FastAPI app."""

    # Example FastAPI integration
    example_code = """
# In your API_files/app.py or wherever you configure FastAPI:

from utils.network_security import create_small_team_security_config, NetworkSecurityManager

 def create_app():
     app = FastAPI()

     # Set up relaxed security for small team
     security_config = create_small_team_security_config()
     security_manager = NetworkSecurityManager(security_config)

     # Add the security middleware
     security_middleware = security_manager.create_middleware()
     app.add_middleware(type(security_middleware), **security_middleware.__dict__)

     # Your existing routes...
     return app
"""

    print("\n📝 FastAPI Integration Code:")
    print(example_code)


if __name__ == "__main__":
    print("🏢 DinoAir Small Team Security Setup")
    print("=" * 50)

    setup_small_team_security()
    integrate_with_fastapi()

    print("\n✅ Your rate limits are now:")
    print("   • 600 requests per minute per IP (10 per second)")
    print("   • No HTTPS requirement for development")
    print("   • 5-minute temporary blocks instead of hours")
    print("   • All common development ports allowed")
    print("\n🎉 Perfect for a 2-person team!")
