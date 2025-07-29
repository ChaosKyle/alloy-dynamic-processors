"""
LDAP Client for Active Directory Integration

Provides authentication and user information retrieval from LDAP/Active Directory servers.
Supports connection pooling, secure connections, and comprehensive user attribute mapping.
"""

import asyncio
import ssl
from typing import Dict, List, Optional, Any
import ldap
import ldap.asyncsearch
from ldap import LDAPError
import structlog
from dataclasses import dataclass

logger = structlog.get_logger(__name__)


@dataclass
class LDAPConfig:
    """LDAP configuration settings"""
    server_uri: str
    bind_dn: str
    bind_password: str
    user_search_base: str
    group_search_base: str
    user_filter: str = "(sAMAccountName={username})"
    group_filter: str = "(member={user_dn})"
    attributes: Dict[str, str] = None
    use_tls: bool = True
    timeout: int = 30
    pool_size: int = 5
    
    def __post_init__(self):
        if self.attributes is None:
            self.attributes = {
                "user_id": "sAMAccountName",
                "display_name": "displayName",
                "email": "mail",
                "first_name": "givenName",
                "last_name": "sn",
                "department": "department",
                "title": "title",
                "manager": "manager",
                "employee_id": "employeeID",
                "phone": "telephoneNumber"
            }


class LDAPConnectionPool:
    """LDAP connection pool for efficient connection management"""
    
    def __init__(self, config: LDAPConfig):
        self.config = config
        self._pool: List[Any] = []
        self._in_use: Dict[Any, bool] = {}
        self._lock = asyncio.Lock()
        
    async def get_connection(self) -> Any:
        """Get a connection from the pool"""
        async with self._lock:
            # Try to find an available connection
            for conn in self._pool:
                if not self._in_use.get(conn, False):
                    self._in_use[conn] = True
                    return conn
            
            # Create new connection if pool not full
            if len(self._pool) < self.config.pool_size:
                conn = await self._create_connection()
                self._pool.append(conn)
                self._in_use[conn] = True
                return conn
            
            # Wait for a connection to become available
            while True:
                for conn in self._pool:
                    if not self._in_use.get(conn, False):
                        self._in_use[conn] = True
                        return conn
                await asyncio.sleep(0.1)
    
    async def return_connection(self, conn: Any):
        """Return a connection to the pool"""
        async with self._lock:
            self._in_use[conn] = False
    
    async def _create_connection(self) -> Any:
        """Create a new LDAP connection"""
        try:
            # Initialize LDAP connection
            conn = ldap.initialize(self.config.server_uri)
            
            # Set LDAP options
            conn.set_option(ldap.OPT_PROTOCOL_VERSION, ldap.VERSION3)
            conn.set_option(ldap.OPT_NETWORK_TIMEOUT, self.config.timeout)
            conn.set_option(ldap.OPT_TIMEOUT, self.config.timeout)
            
            if self.config.use_tls:
                # Configure TLS settings
                conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
                conn.set_option(ldap.OPT_X_TLS_NEWCTX, 0)
                conn.start_tls_s()
            
            # Bind with service account
            conn.simple_bind_s(self.config.bind_dn, self.config.bind_password)
            
            logger.debug("LDAP connection created", server=self.config.server_uri)
            return conn
            
        except LDAPError as e:
            logger.error("Failed to create LDAP connection", error=str(e))
            raise
    
    async def close_all(self):
        """Close all connections in the pool"""
        async with self._lock:
            for conn in self._pool:
                try:
                    conn.unbind_s()
                except:
                    pass
            self._pool.clear()
            self._in_use.clear()


class LDAPClient:
    """LDAP client for user authentication and information retrieval"""
    
    def __init__(self, config: LDAPConfig):
        self.config = config
        self.pool = LDAPConnectionPool(config)
        
    async def test_connection(self) -> bool:
        """Test LDAP server connectivity"""
        try:
            conn = await self.pool.get_connection()
            
            # Perform a simple search to test connectivity
            result = conn.search_s(
                self.config.user_search_base,
                ldap.SCOPE_BASE,
                "(objectClass=*)",
                []
            )
            
            await self.pool.return_connection(conn)
            logger.info("LDAP connection test successful")
            return True
            
        except Exception as e:
            logger.error("LDAP connection test failed", error=str(e))
            return False
    
    async def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate user credentials against LDAP"""
        try:
            logger.debug("Authenticating user", username=username)
            
            # Get user DN and attributes
            user_info = await self._get_user_info(username)
            if not user_info:
                logger.warning("User not found in LDAP", username=username)
                return None
            
            user_dn = user_info["dn"]
            
            # Try to bind with user credentials
            try:
                auth_conn = ldap.initialize(self.config.server_uri)
                auth_conn.set_option(ldap.OPT_PROTOCOL_VERSION, ldap.VERSION3)
                auth_conn.set_option(ldap.OPT_NETWORK_TIMEOUT, self.config.timeout)
                
                if self.config.use_tls:
                    auth_conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
                    auth_conn.start_tls_s()
                
                # Attempt to bind with user credentials
                auth_conn.simple_bind_s(user_dn, password)
                auth_conn.unbind_s()
                
                logger.info("User authentication successful", username=username)
                
                # Return user information (without sensitive data)
                return {
                    "user_id": user_info.get("user_id"),
                    "display_name": user_info.get("display_name", username),
                    "email": user_info.get("email", ""),
                    "first_name": user_info.get("first_name", ""),
                    "last_name": user_info.get("last_name", ""),
                    "department": user_info.get("department", ""),
                    "title": user_info.get("title", ""),
                    "employee_id": user_info.get("employee_id", "")
                }
                
            except ldap.INVALID_CREDENTIALS:
                logger.warning("Invalid credentials for user", username=username)
                return None
            except LDAPError as e:
                logger.error("LDAP authentication error", username=username, error=str(e))
                return None
                
        except Exception as e:
            logger.error("Authentication error", username=username, error=str(e))
            return None
    
    async def _get_user_info(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user information from LDAP"""
        try:
            conn = await self.pool.get_connection()
            
            # Search for user
            search_filter = self.config.user_filter.format(username=username)
            attributes = list(self.config.attributes.values()) + ["dn"]
            
            results = conn.search_s(
                self.config.user_search_base,
                ldap.SCOPE_SUBTREE,
                search_filter,
                attributes
            )
            
            await self.pool.return_connection(conn)
            
            if not results:
                return None
            
            dn, attrs = results[0]
            
            # Map LDAP attributes to user info
            user_info = {"dn": dn}
            for key, ldap_attr in self.config.attributes.items():
                value = attrs.get(ldap_attr, [])
                if value:
                    # LDAP returns bytes, decode to string
                    if isinstance(value[0], bytes):
                        user_info[key] = value[0].decode('utf-8')
                    else:
                        user_info[key] = value[0]
                else:
                    user_info[key] = ""
            
            return user_info
            
        except Exception as e:
            logger.error("Error getting user info", username=username, error=str(e))
            return None
    
    async def get_user_groups(self, username: str) -> List[str]:
        """Get user group memberships from LDAP"""
        try:
            logger.debug("Getting user groups", username=username)
            
            # First get user DN
            user_info = await self._get_user_info(username)
            if not user_info:
                return []
            
            user_dn = user_info["dn"]
            
            conn = await self.pool.get_connection()
            
            # Search for groups where user is a member
            search_filter = self.config.group_filter.format(user_dn=user_dn)
            
            results = conn.search_s(
                self.config.group_search_base,
                ldap.SCOPE_SUBTREE,
                search_filter,
                ["cn", "name", "displayName"]
            )
            
            await self.pool.return_connection(conn)
            
            groups = []
            for dn, attrs in results:
                # Try different attributes for group name
                group_name = None
                for attr in ["cn", "name", "displayName"]:
                    if attr in attrs and attrs[attr]:
                        group_name = attrs[attr][0]
                        if isinstance(group_name, bytes):
                            group_name = group_name.decode('utf-8')
                        break
                
                if group_name:
                    groups.append(group_name)
            
            logger.debug("Found user groups", username=username, groups=groups)
            return groups
            
        except Exception as e:
            logger.error("Error getting user groups", username=username, error=str(e))
            return []
    
    async def search_users(self, search_term: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search for users in LDAP"""
        try:
            conn = await self.pool.get_connection()
            
            # Create search filter for multiple attributes
            search_filter = f"(|({self.config.attributes['user_id']}=*{search_term}*)" \
                          f"({self.config.attributes['display_name']}=*{search_term}*)" \
                          f"({self.config.attributes['email']}=*{search_term}*))"
            
            attributes = list(self.config.attributes.values())
            
            results = conn.search_s(
                self.config.user_search_base,
                ldap.SCOPE_SUBTREE,
                search_filter,
                attributes
            )
            
            await self.pool.return_connection(conn)
            
            users = []
            for dn, attrs in results[:limit]:
                user_info = {}
                for key, ldap_attr in self.config.attributes.items():
                    value = attrs.get(ldap_attr, [])
                    if value:
                        if isinstance(value[0], bytes):
                            user_info[key] = value[0].decode('utf-8')
                        else:
                            user_info[key] = value[0]
                    else:
                        user_info[key] = ""
                
                users.append(user_info)
            
            return users
            
        except Exception as e:
            logger.error("Error searching users", search_term=search_term, error=str(e))
            return []
    
    async def get_group_members(self, group_name: str) -> List[str]:
        """Get members of a specific group"""
        try:
            conn = await self.pool.get_connection()
            
            # Search for the group
            search_filter = f"(cn={group_name})"
            
            results = conn.search_s(
                self.config.group_search_base,
                ldap.SCOPE_SUBTREE,
                search_filter,
                ["member"]
            )
            
            await self.pool.return_connection(conn)
            
            if not results:
                return []
            
            dn, attrs = results[0]
            members = attrs.get("member", [])
            
            # Extract usernames from member DNs
            usernames = []
            for member_dn in members:
                if isinstance(member_dn, bytes):
                    member_dn = member_dn.decode('utf-8')
                
                # Extract username from DN (assumes CN=username format)
                if "CN=" in member_dn:
                    username = member_dn.split("CN=")[1].split(",")[0]
                    usernames.append(username)
            
            return usernames
            
        except Exception as e:
            logger.error("Error getting group members", group_name=group_name, error=str(e))
            return []
    
    async def close(self):
        """Close LDAP connection pool"""
        await self.pool.close_all()
        logger.info("LDAP client closed")