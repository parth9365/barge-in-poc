# NovaBoard - Troubleshooting Guide

## Login and Account Issues

### Cannot Log In

**Symptoms**: Login page shows "Invalid credentials" or spins indefinitely.

**Solutions**:
1. **Check your email address**: Ensure you're using the email associated with your NovaBoard account. If your organization uses SSO, you may need to use your corporate email.
2. **Reset your password**: Click "Forgot Password" on the login page. The reset email arrives within 5 minutes. Check your spam folder.
3. **Clear browser cache**: Go to your browser settings and clear cookies and cached data for novaboard.example.com.
4. **Try a different browser**: NovaBoard supports Chrome 90+, Firefox 88+, Safari 15+, and Edge 90+. Internet Explorer is not supported.
5. **Check SSO configuration**: If your organization uses SSO/SAML, contact your IT administrator. The SSO endpoint may need to be reconfigured. Common issue: SAML certificate expiration.
6. **Account locked**: After 5 failed login attempts, accounts are locked for 30 minutes. Wait or contact support.

### Two-Factor Authentication (2FA) Issues

**Lost your 2FA device?** Contact your organization admin to reset 2FA. Admins can do this from **Admin Settings > Users > [User] > Reset 2FA**. If you saved your recovery codes during 2FA setup, use one of those codes to log in.

### Account Deactivated

If your account has been deactivated, you'll see "Account Suspended" on login. This happens when:
- Your organization admin has deactivated your account
- Your organization's subscription has expired
- Your account was flagged for Terms of Service violation

Contact your organization admin or NovaTech support to resolve.

## Sync and Data Issues

### Tasks Not Syncing Across Devices

**Symptoms**: Changes made on one device don't appear on another.

**Solutions**:
1. **Check your internet connection**: NovaBoard requires an active connection to sync. Offline changes sync when you reconnect.
2. **Force refresh**: Press Ctrl+Shift+R (Cmd+Shift+R on Mac) to force a full page refresh.
3. **Check sync status**: Look at the sync indicator in the bottom-left corner of NovaBoard. Green = synced, yellow = syncing, red = error.
4. **Mobile app sync**: Pull down on the main screen to force a sync. If that fails, log out and log back in.
5. **Browser extensions**: Ad blockers or privacy extensions may block NovaBoard's WebSocket connections. Try disabling extensions or adding novaboard.example.com to your allowlist.

### Missing Tasks or Projects

**Possible causes**:
1. **Filters active**: Check if you have filters applied. Click "Clear Filters" in the top bar.
2. **Wrong workspace**: You may be looking at a different workspace. Check the workspace selector in the top-left corner.
3. **Permissions**: You may not have access to the project. Ask the project admin to add you.
4. **Archived**: The project or task may have been archived. Go to **Settings > Archived Items** to check.
5. **Deleted**: Deleted items are retained for 30 days. Contact support to restore within that window.

### Data Export Issues

**Problem**: Export to CSV/JSON/PDF fails or produces empty file.

**Solutions**:
1. **Large datasets**: Exports with more than 10,000 tasks may time out. Use the API with pagination instead.
2. **Browser popup blocker**: Exports open in a new tab. Allow popups from novaboard.example.com.
3. **Custom fields**: Exports include all default fields. Custom fields are included in CSV and JSON but not PDF.
4. **Date range**: Apply a date range filter before exporting to reduce dataset size.

## Integration Issues

### GitHub Integration Not Working

**Symptoms**: Commits and PRs are not being linked to NovaBoard tasks.

**Solutions**:
1. **Check connection status**: Go to **Settings > Integrations > GitHub** and verify the connection is active.
2. **Repository access**: Ensure the NovaBoard GitHub App has access to the relevant repositories. Go to your GitHub organization settings > Installed GitHub Apps > NovaBoard > Repository access.
3. **Task ID format**: NovaBoard links commits containing the task ID in the format `NB-1234` in the commit message or branch name. Ensure your commits include this pattern.
4. **Webhook delivery**: Check GitHub webhook delivery logs at Settings > Webhooks > Recent Deliveries in your GitHub repo. Failed deliveries show error codes.
5. **Re-authorize**: Disconnect and reconnect the GitHub integration. This refreshes the OAuth tokens.

### Slack Integration Issues

**Symptoms**: Slack notifications not arriving, slash commands not working.

**Solutions**:
1. **Re-install the Slack app**: Go to **Settings > Integrations > Slack > Reinstall**.
2. **Channel permissions**: Ensure the NovaBoard bot has been invited to the relevant Slack channels. Type `/invite @NovaBoard` in the channel.
3. **Notification preferences**: Check **Settings > Notifications > Slack** to ensure notifications are enabled for the events you want.
4. **Slash commands**: The `/nova` command requires the Pro or Enterprise plan. Free plan users cannot use slash commands.
5. **Slack workspace change**: If your Slack workspace URL changed, you'll need to re-authorize the integration.

## Performance Issues

### NovaBoard Loading Slowly

**Solutions**:
1. **Check system status**: Visit status.novaboard.example.com for current service status and known issues.
2. **Browser performance**: Close unused tabs. NovaBoard works best with less than 50 browser tabs open.
3. **Large boards**: Boards with more than 500 visible cards may load slowly. Use filters or WIP limits to reduce visible items.
4. **Browser cache**: Clear your browser cache. Stale cached assets can cause performance issues.
5. **Network**: Use a wired connection if possible. Minimum recommended bandwidth: 2 Mbps.
6. **Disable animations**: Go to **Settings > Accessibility > Reduce Motion** to disable board animations.

### Search Not Returning Expected Results

**Solutions**:
1. **Search scope**: By default, search covers the current project. Use the global search (Ctrl+K / Cmd+K) to search across all projects.
2. **Archived items**: Search does not include archived items by default. Toggle "Include Archived" in search options.
3. **Search syntax**: Use quotes for exact phrases ("deployment error"). Use labels:bug to search by label. Use assignee:me to filter by assignment.
4. **Indexing delay**: New tasks may take up to 60 seconds to appear in search results.

## Notification Issues

### Not Receiving Email Notifications

**Solutions**:
1. **Check notification settings**: Go to **Settings > Notifications > Email** and ensure the relevant events are enabled.
2. **Spam folder**: Check your email spam/junk folder. Add notifications@novaboard.example.com to your contacts.
3. **Email frequency**: NovaBoard batches notifications. Choose between "Immediate", "Hourly Digest", or "Daily Digest" in settings.
4. **Unsubscribed**: You may have clicked "Unsubscribe" on a previous email. Re-enable in notification settings.
5. **Organizational email policies**: Some organizations block external email. Contact your IT team to allowlist novaboard.example.com.

### Push Notifications Not Working (Mobile)

**Solutions**:
1. **OS permissions**: Ensure NovaBoard has notification permissions in your device settings (iOS: Settings > Notifications > NovaBoard; Android: Settings > Apps > NovaBoard > Notifications).
2. **App version**: Update to the latest version of the NovaBoard app. Notifications may not work on outdated versions.
3. **Battery optimization**: On Android, disable battery optimization for NovaBoard (Settings > Battery > Battery Optimization > NovaBoard > Don't Optimize).
4. **Do Not Disturb**: Check if DND mode is active on your device.

## Billing Issues

### Charge Not Expected

If you see an unexpected charge:
1. **Annual billing**: Annual plans are charged in full at the start of the billing cycle.
2. **New team members**: Adding users mid-cycle triggers a prorated charge.
3. **Plan upgrade**: Upgrading from Free to Pro triggers an immediate prorated charge.
4. Contact billing@novatech.example.com with your organization name and the charge amount for investigation.

### Invoice Needed

Go to **Settings > Billing > Invoice History** to download invoices as PDF. Enterprise customers with custom billing should contact their customer success manager.
