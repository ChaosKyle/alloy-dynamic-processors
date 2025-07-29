"""
SAML SSO Client for Enterprise Identity Provider Integration

Supports SAML 2.0 authentication with enterprise identity providers like Okta, Azure AD,
ADFS, and other SAML-compliant systems. Provides comprehensive attribute mapping and
security validation.
"""

import base64
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse, parse_qs
import structlog
from dataclasses import dataclass
from datetime import datetime, timedelta
import uuid

from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.settings import OneLogin_Saml2_Settings
from onelogin.saml2.utils import OneLogin_Saml2_Utils

logger = structlog.get_logger(__name__)


@dataclass
class SAMLConfig:
    """SAML configuration settings"""
    # Service Provider (SP) settings
    sp_entity_id: str
    sp_assertion_consumer_service_url: str
    sp_single_logout_service_url: str
    sp_name_id_format: str = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
    sp_x509_cert: str = ""
    sp_private_key: str = ""
    
    # Identity Provider (IdP) settings
    idp_entity_id: str
    idp_single_sign_on_service_url: str
    idp_single_logout_service_url: str
    idp_x509_cert: str
    
    # Security settings
    want_assertions_signed: bool = True
    want_name_id_encrypted: bool = False
    want_assertions_encrypted: bool = False
    sign_metadata: bool = True
    sign_authentication_requests: bool = True
    sign_logout_request: bool = True
    sign_logout_response: bool = True
    
    # Attribute mapping
    attribute_mapping: Dict[str, str] = None
    
    # Session settings
    session_lifetime_hours: int = 8
    max_clock_skew_seconds: int = 300
    
    def __post_init__(self):
        if self.attribute_mapping is None:
            self.attribute_mapping = {
                "user_id": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name",
                "email": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
                "display_name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/displayname",
                "first_name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname",
                "last_name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname",
                "groups": "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups",
                "department": "http://schemas.xmlsoap.org/claims/Department",
                "title": "http://schemas.xmlsoap.org/claims/Title",
                "employee_id": "http://schemas.xmlsoap.org/claims/EmployeeID"
            }


class SAMLClient:
    """SAML client for SSO authentication"""
    
    def __init__(self, config: SAMLConfig):
        self.config = config
        self._saml_settings = self._build_saml_settings()
        
    def _build_saml_settings(self) -> Dict[str, Any]:
        """Build SAML settings dictionary for OneLogin SAML library"""
        return {
            "sp": {
                "entityId": self.config.sp_entity_id,
                "assertionConsumerService": {
                    "url": self.config.sp_assertion_consumer_service_url,
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
                },
                "singleLogoutService": {
                    "url": self.config.sp_single_logout_service_url,
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
                },
                "NameIDFormat": self.config.sp_name_id_format,
                "x509cert": self.config.sp_x509_cert,
                "privateKey": self.config.sp_private_key
            },
            "idp": {
                "entityId": self.config.idp_entity_id,
                "singleSignOnService": {
                    "url": self.config.idp_single_sign_on_service_url,
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
                },
                "singleLogoutService": {
                    "url": self.config.idp_single_logout_service_url,
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
                },
                "x509cert": self.config.idp_x509_cert
            },
            "security": {
                "nameIdEncrypted": self.config.want_name_id_encrypted,
                "authnRequestsSigned": self.config.sign_authentication_requests,
                "logoutRequestSigned": self.config.sign_logout_request,
                "logoutResponseSigned": self.config.sign_logout_response,
                "signMetadata": self.config.sign_metadata,
                "wantAssertionsSigned": self.config.want_assertions_signed,
                "wantAssertionsEncrypted": self.config.want_assertions_encrypted,
                "wantNameId": True,
                "wantNameIdEncrypted": self.config.want_name_id_encrypted,
                "requestedAuthnContext": True,
                "requestedAuthnContextComparison": "exact",
                "wantXMLValidation": True,
                "signatureAlgorithm": "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
                "digestAlgorithm": "http://www.w3.org/2001/04/xmlenc#sha256"
            }
        }
    
    async def get_login_url(self, relay_state: Optional[str] = None) -> str:
        """Generate SAML authentication request URL"""
        try:
            # Create fake request object for OneLogin SAML library
            fake_request = {
                'https': 'on' if self.config.sp_assertion_consumer_service_url.startswith('https') else 'off',
                'http_host': urlparse(self.config.sp_assertion_consumer_service_url).netloc,
                'server_port': '443' if self.config.sp_assertion_consumer_service_url.startswith('https') else '80',
                'script_name': '',
                'get_data': {},
                'post_data': {}
            }
            
            auth = OneLogin_Saml2_Auth(fake_request, self._saml_settings)
            
            # Generate login URL
            login_url = auth.login(return_to=relay_state)
            
            logger.info("Generated SAML login URL", relay_state=relay_state)
            return login_url
            
        except Exception as e:
            logger.error("Error generating SAML login URL", error=str(e))
            raise
    
    async def validate_response(self, saml_response: str, relay_state: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Validate SAML response and extract user information"""
        try:
            logger.debug("Validating SAML response", relay_state=relay_state)
            
            # Create fake request object for OneLogin SAML library
            fake_request = {
                'https': 'on' if self.config.sp_assertion_consumer_service_url.startswith('https') else 'off',
                'http_host': urlparse(self.config.sp_assertion_consumer_service_url).netloc,
                'server_port': '443' if self.config.sp_assertion_consumer_service_url.startswith('https') else '80',
                'script_name': '',
                'get_data': {},
                'post_data': {
                    'SAMLResponse': saml_response,
                    'RelayState': relay_state or ''
                }
            }
            
            auth = OneLogin_Saml2_Auth(fake_request, self._saml_settings)
            
            # Process SAML response
            auth.process_response()
            
            # Check for errors
            errors = auth.get_errors()
            if errors:
                logger.error("SAML response validation errors", errors=errors)
                return None
            
            # Verify authentication status
            if not auth.is_authenticated():
                logger.warning("SAML authentication failed")
                return None
            
            # Extract user attributes
            attributes = auth.get_attributes()
            name_id = auth.get_nameid()
            
            logger.debug("SAML response validated successfully", 
                        name_id=name_id, 
                        attributes=list(attributes.keys()))
            
            # Map SAML attributes to user info
            user_info = await self._map_attributes(attributes, name_id)
            
            # Validate assertion conditions
            if not await self._validate_assertion_conditions(auth):
                logger.error("SAML assertion conditions validation failed")
                return None
            
            logger.info("SAML authentication successful", user_id=user_info.get("user_id"))
            return user_info
            
        except Exception as e:
            logger.error("Error validating SAML response", error=str(e))
            return None
    
    async def _map_attributes(self, attributes: Dict[str, List[str]], name_id: str) -> Dict[str, Any]:
        """Map SAML attributes to user information"""
        user_info = {
            "user_id": name_id,  # Fallback to NameID
            "display_name": "",
            "email": "",
            "first_name": "",
            "last_name": "",
            "groups": [],
            "department": "",
            "title": "",
            "employee_id": ""
        }
        
        # Map each configured attribute
        for field, saml_attr in self.config.attribute_mapping.items():
            if saml_attr in attributes and attributes[saml_attr]:
                value = attributes[saml_attr]
                
                if field == "groups":
                    # Groups can be multi-valued
                    user_info[field] = value if isinstance(value, list) else [value]
                else:
                    # Single-valued attributes
                    user_info[field] = value[0] if isinstance(value, list) else value
        
        # Use email as user_id if available and user_id is still NameID
        if user_info["email"] and user_info["user_id"] == name_id:
            user_info["user_id"] = user_info["email"]
        
        # Generate display name if not provided
        if not user_info["display_name"]:
            if user_info["first_name"] and user_info["last_name"]:
                user_info["display_name"] = f"{user_info['first_name']} {user_info['last_name']}"
            elif user_info["email"]:
                user_info["display_name"] = user_info["email"].split("@")[0]
            else:
                user_info["display_name"] = user_info["user_id"]
        
        return user_info
    
    async def _validate_assertion_conditions(self, auth: OneLogin_Saml2_Auth) -> bool:
        """Validate SAML assertion conditions (time, audience, etc.)"""
        try:
            # Get the SAML response XML
            response = auth.get_last_response_xml()
            if not response:
                return False
            
            # Parse XML
            root = ET.fromstring(response)
            
            # Find assertion element
            assertion = root.find('.//{urn:oasis:names:tc:SAML:2.0:assertion}Assertion')
            if assertion is None:
                logger.error("No assertion found in SAML response")
                return False
            
            # Check conditions
            conditions = assertion.find('.//{urn:oasis:names:tc:SAML:2.0:assertion}Conditions')
            if conditions is not None:
                # Check NotBefore
                not_before = conditions.get('NotBefore')
                if not_before:
                    not_before_time = datetime.fromisoformat(not_before.replace('Z', '+00:00'))
                    if datetime.now().timestamp() < (not_before_time.timestamp() - self.config.max_clock_skew_seconds):
                        logger.error("SAML assertion not yet valid", not_before=not_before)
                        return False
                
                # Check NotOnOrAfter
                not_on_or_after = conditions.get('NotOnOrAfter')
                if not_on_or_after:
                    not_on_or_after_time = datetime.fromisoformat(not_on_or_after.replace('Z', '+00:00'))
                    if datetime.now().timestamp() > (not_on_or_after_time.timestamp() + self.config.max_clock_skew_seconds):
                        logger.error("SAML assertion expired", not_on_or_after=not_on_or_after)
                        return False
                
                # Check audience restriction
                audience_restriction = conditions.find('.//{urn:oasis:names:tc:SAML:2.0:assertion}AudienceRestriction')
                if audience_restriction is not None:
                    audience = audience_restriction.find('.//{urn:oasis:names:tc:SAML:2.0:assertion}Audience')
                    if audience is not None and audience.text != self.config.sp_entity_id:
                        logger.error("SAML assertion audience mismatch", 
                                   expected=self.config.sp_entity_id, 
                                   actual=audience.text)
                        return False
            
            return True
            
        except Exception as e:
            logger.error("Error validating assertion conditions", error=str(e))
            return False
    
    async def get_logout_url(self, name_id: str, session_index: Optional[str] = None, 
                           relay_state: Optional[str] = None) -> str:
        """Generate SAML logout request URL"""
        try:
            # Create fake request object
            fake_request = {
                'https': 'on' if self.config.sp_single_logout_service_url.startswith('https') else 'off',
                'http_host': urlparse(self.config.sp_single_logout_service_url).netloc,
                'server_port': '443' if self.config.sp_single_logout_service_url.startswith('https') else '80',
                'script_name': '',
                'get_data': {},
                'post_data': {}
            }
            
            auth = OneLogin_Saml2_Auth(fake_request, self._saml_settings)
            
            # Generate logout URL
            logout_url = auth.logout(
                return_to=relay_state,
                name_id=name_id,
                session_index=session_index
            )
            
            logger.info("Generated SAML logout URL", name_id=name_id)
            return logout_url
            
        except Exception as e:
            logger.error("Error generating SAML logout URL", error=str(e))
            raise
    
    async def process_logout_response(self, saml_response: str) -> bool:
        """Process SAML logout response"""
        try:
            # Create fake request object
            fake_request = {
                'https': 'on' if self.config.sp_single_logout_service_url.startswith('https') else 'off',
                'http_host': urlparse(self.config.sp_single_logout_service_url).netloc,
                'server_port': '443' if self.config.sp_single_logout_service_url.startswith('https') else '80',
                'script_name': '',
                'get_data': {
                    'SAMLResponse': saml_response
                },
                'post_data': {}
            }
            
            auth = OneLogin_Saml2_Auth(fake_request, self._saml_settings)
            
            # Process logout response
            url = auth.process_slo(delete_session_cb=lambda: None)
            
            # Check for errors
            errors = auth.get_errors()
            if errors:
                logger.error("SAML logout response errors", errors=errors)
                return False
            
            logger.info("SAML logout processed successfully")
            return True
            
        except Exception as e:
            logger.error("Error processing SAML logout response", error=str(e))
            return False
    
    async def get_metadata(self) -> str:
        """Generate SAML SP metadata XML"""
        try:
            settings = OneLogin_Saml2_Settings(self._saml_settings)
            metadata = settings.get_sp_metadata()
            
            # Validate metadata
            errors = settings.check_sp_metadata(metadata)
            if errors:
                logger.error("SAML metadata validation errors", errors=errors)
                raise ValueError(f"Invalid SAML metadata: {errors}")
            
            logger.info("Generated SAML SP metadata")
            return metadata
            
        except Exception as e:
            logger.error("Error generating SAML metadata", error=str(e))
            raise
    
    async def validate_metadata(self) -> bool:
        """Validate SAML configuration"""
        try:
            settings = OneLogin_Saml2_Settings(self._saml_settings)
            
            # Check SP settings
            sp_errors = settings.check_sp_settings()
            if sp_errors:
                logger.error("SAML SP configuration errors", errors=sp_errors)
                return False
            
            # Check IdP settings
            idp_errors = settings.check_idp_settings()
            if idp_errors:
                logger.error("SAML IdP configuration errors", errors=idp_errors)
                return False
            
            logger.info("SAML configuration validation successful")
            return True
            
        except Exception as e:
            logger.error("Error validating SAML configuration", error=str(e))
            return False