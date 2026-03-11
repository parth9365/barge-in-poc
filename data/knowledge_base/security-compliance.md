# NovaBoard - Security and Compliance

## Security Overview

NovaTech takes security seriously. NovaBoard is built on a security-first architecture with multiple layers of protection for your data. Our security program is led by a dedicated team of 8 security engineers and is reviewed annually by independent third-party auditors.

## Data Encryption

### In Transit
All data transmitted between your browser and NovaBoard servers is encrypted using TLS 1.3. We enforce HSTS (HTTP Strict Transport Security) with a minimum age of 1 year. All API communications require HTTPS -- plaintext HTTP requests are rejected.

### At Rest
All customer data stored in NovaBoard is encrypted at rest using AES-256 encryption. Database encryption is managed through AWS KMS (Key Management Service) with automatic key rotation every 365 days. File attachments are encrypted using server-side encryption with S3-managed keys (SSE-S3).

### Field-Level Encryption
Enterprise customers with the Advanced Security add-on can enable field-level encryption for sensitive custom fields. This uses envelope encryption where each field value has its own data encryption key (DEK), wrapped by a customer-managed key encryption key (KEK) in AWS KMS.

## Authentication and Access Control

### Password Policy
- Minimum 12 characters
- Must include uppercase, lowercase, number, and special character
- Passwords are hashed using bcrypt with a cost factor of 12
- Password history: last 5 passwords cannot be reused
- Account lockout after 5 failed attempts (30-minute lockout)

### Single Sign-On (SSO)
Enterprise plan includes SSO support:
- **SAML 2.0**: Compatible with Okta, Azure AD, OneLogin, PingFederate, and other SAML 2.0 identity providers.
- **OAuth 2.0 / OIDC**: Supports Google Workspace, Microsoft Entra ID, and custom OIDC providers.
- **Just-in-Time (JIT) provisioning**: New users are automatically created on first SSO login.
- **Forced SSO**: Admins can enforce SSO-only login, disabling email/password authentication.

### SCIM Provisioning
Enterprise plan supports SCIM 2.0 for automated user lifecycle management:
- Automatic user creation and deactivation
- Group-to-team mapping
- Attribute synchronization (name, email, department)
- Supported providers: Okta, Azure AD, OneLogin

### Multi-Factor Authentication (MFA)
All plans support optional MFA. Enterprise admins can enforce MFA organization-wide.
- **TOTP**: Compatible with Google Authenticator, Authy, 1Password, etc.
- **WebAuthn/FIDO2**: Hardware security keys (YubiKey, Titan) and platform authenticators (Touch ID, Windows Hello).
- **Recovery codes**: 10 one-time codes generated at MFA setup.

### Role-Based Access Control (RBAC)
NovaBoard supports four built-in roles:
- **Owner**: Full access. Can manage billing, delete organization.
- **Admin**: Full project access. Can manage users, settings, and integrations.
- **Member**: Can create and manage tasks in projects they belong to.
- **Viewer**: Read-only access to projects they belong to.

Enterprise customers can create custom roles with granular permissions (e.g., "can create tasks but not delete", "can view reports but not export").

## Compliance Certifications

### SOC 2 Type II
NovaTech has maintained SOC 2 Type II compliance since 2022. Our annual audit covers the Trust Services Criteria for Security, Availability, and Confidentiality. The most recent audit was completed in January 2025 by Ernst & Young. Request our SOC 2 report at security@novatech.example.com.

### GDPR
NovaTech is fully compliant with the EU General Data Protection Regulation:
- **Data Processing Agreement (DPA)**: Available for all customers at novatech.example.com/legal/dpa.
- **Data Subject Rights**: Users can request data export, correction, or deletion via **Settings > Privacy > My Data**.
- **Data Portability**: Full data export in machine-readable JSON format.
- **Right to Erasure**: Data deletion requests are processed within 30 days.
- **Data Protection Officer**: Contact dpo@novatech.example.com.
- **EU Data Residency**: Enterprise customers can choose EU data storage (Ireland region) with the Data Residency add-on.

### ISO 27001
NovaTech is ISO 27001:2022 certified. Our Information Security Management System (ISMS) covers all aspects of NovaBoard's development, operations, and support. Certificate available upon request.

### HIPAA
Healthcare organizations can achieve HIPAA compliance with the Enterprise Advanced Security add-on:
- Business Associate Agreement (BAA) available
- Field-level encryption for PHI
- Audit logging with 7-year retention
- Access controls meeting HIPAA minimum necessary standard
- Automatic session timeout (configurable, default 15 minutes)

### SOX
NovaBoard supports SOX compliance requirements:
- Segregation of duties through RBAC
- Comprehensive audit trails
- Change management controls
- Automated access reviews (quarterly)

## Infrastructure Security

### Hosting
NovaBoard is hosted on Amazon Web Services (AWS) in the following regions:
- **Primary**: US East (N. Virginia) - us-east-1
- **EU**: Europe (Ireland) - eu-west-1 (Enterprise Data Residency add-on)
- **APAC**: Asia Pacific (Singapore) - ap-southeast-1 (Enterprise Data Residency add-on)

### Network Security
- All traffic routed through AWS CloudFront CDN with WAF (Web Application Firewall)
- DDoS protection via AWS Shield Advanced
- VPC with private subnets for application and database tiers
- Network segmentation between customer environments
- IP allowlisting available on Enterprise plan

### Vulnerability Management
- Automated dependency scanning with Dependabot and Snyk
- Weekly automated penetration testing with Burp Suite
- Annual third-party penetration test by NCC Group
- Bug bounty program: Report vulnerabilities to security@novatech.example.com (rewards up to $5,000)
- Critical vulnerabilities patched within 24 hours, high within 7 days

### Incident Response
- 24/7 security monitoring via SIEM (Splunk)
- Automated alerting for suspicious activity
- Incident response team on-call with 15-minute response SLA
- Customer notification within 72 hours of confirmed data breach (per GDPR requirements)
- Post-incident review published within 5 business days

## Data Retention and Deletion

### Default Retention
- **Active accounts**: Data retained indefinitely while account is active.
- **Deleted tasks/projects**: Soft-deleted, retained for 30 days, then permanently purged.
- **Closed accounts**: Data retained for 30 days after account closure, then permanently deleted.
- **Audit logs**: Retained for 1 year (standard) or 2 years (Enterprise).

### Custom Retention (Enterprise)
Enterprise customers can configure custom retention policies:
- Set retention periods per data type (tasks, comments, attachments, audit logs)
- Minimum retention: 30 days
- Maximum retention: 7 years (for HIPAA/SOX compliance)
- Automated purge notifications to admins before data deletion

### Data Deletion Process
When data is permanently deleted:
1. Records removed from primary database
2. Backup copies purged within 30 days (backup rotation cycle)
3. Search index entries cleared within 24 hours
4. File attachments deleted from S3 within 7 days
5. Deletion confirmation available upon request

## Security Best Practices for Customers

1. **Enable MFA** for all team members, especially admins
2. **Use SSO** to centralize authentication and reduce password sprawl
3. **Review access regularly**: Audit project memberships quarterly
4. **Use API key scoping**: Create read-only API keys when write access is not needed
5. **Monitor audit logs**: Review admin actions and unusual login patterns
6. **Set up IP allowlisting**: Restrict access to known corporate IP ranges (Enterprise)
7. **Enable session timeout**: Configure automatic logout after inactivity (default: 8 hours, configurable to 15 minutes)

## Contact Security Team

- **Security inquiries**: security@novatech.example.com
- **Bug bounty reports**: security@novatech.example.com (subject: "Bug Bounty")
- **SOC 2 report requests**: security@novatech.example.com
- **DPA requests**: legal@novatech.example.com
- **Privacy/GDPR**: dpo@novatech.example.com
