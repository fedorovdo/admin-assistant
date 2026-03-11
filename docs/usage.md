# Usage Guide

This guide walks through the main day-to-day workflows in Admin Assistant.

## Main UI Layout

### Left Sidebar

**Servers**

Use this area to:

- add servers
- edit server settings
- delete servers
- test SSH connectivity
- select one or many target hosts

**Scripts**

Use this area to:

- create reusable scripts
- edit existing scripts
- delete scripts
- choose which script should run in Script mode

### Center Panel

**Execution**

Use this tab to:

- run manual commands
- run scripts
- review live output
- analyze the latest completed run
- start Incident Mode

**History**

Use this tab to:

- browse previous runs
- inspect host status
- replay output
- review linked AI analysis and action relationships

### Right Panel

Use the AI panel to:

- configure the AI provider
- change analysis language
- read the AI summary
- review suggested actions
- review fix plans
- approve, reject, or execute approved steps

## Typical Workflow: Add a Server

1. In **Servers**, click `Add`.
2. Enter the host, username, and authentication method.
3. Save.
4. Select the server and click `Test`.

If the test fails:

- verify SSH port and credentials
- verify host key behavior
- check the app log if needed

## Typical Workflow: Run a Manual Command

1. Select one or more servers.
2. In the Execution tab, choose `Manual Command`.
3. Choose `bash` or `sh`.
4. Enter a command such as:

```bash
uptime
free -h
df -h
journalctl -u sshd -n 50 --no-pager
```

5. Optionally enable:
   - `Run with sudo`
   - `Allocate PTY`
6. Click `Run`.

Output appears in:

- `All Hosts`
- one tab per host

## Typical Workflow: Run a Script

1. Create a script in the Scripts panel.
2. Select one or more servers.
3. Switch to `Script` mode.
4. Verify the chosen script is displayed.
5. Click `Run`.

## Understanding Execution Controls

### Run with sudo

Use when the remote command requires elevated privileges.

Example:

```bash
systemctl status sshd --no-pager
```

### Allocate PTY

Use when a command needs a terminal.

For most simple read-only diagnostics, you may not need it. Some sudo scenarios require it.

### Stop

The top Stop button is the active run control in the Execution panel.

This matters especially when:

- a long run is active
- an approved AI action was launched from the AI panel
- Incident Mode is running diagnostics through the Execution flow

## Typical Workflow: AI Analysis

1. Run a command or script.
2. Wait for the run to complete.
3. Click `Analyze`.

The AI panel can return:

- summary
- probable causes
- evidence
- next steps
- suggested actions
- fix plan

## Typical Workflow: Suggested Actions

1. Select a suggested action or a fix step.
2. Review:
   - title
   - command text
   - risk level
   - status
3. Click:
   - `Approve`
   - `Reject`
   - `Execute Approved`

Only approved actions can be executed.

Admin Assistant applies safety rules to block unsafe AI-generated commands such as:

- nested SSH commands
- interactive commands
- long-running streaming commands
- risky SSH remediation commands

## Typical Workflow: Incident Mode

1. Select one or more servers.
2. Click `Investigate`.
3. Enter a short incident title and symptom.
4. Admin Assistant will:
   - classify the incident
   - generate a safe investigation plan
   - filter unsafe steps
   - run safe diagnostics
   - analyze the evidence
5. Review the final incident analysis in the AI panel.

Example symptoms:

- `ssh login fails on web server`
- `disk usage alert on db host`
- `high cpu on application server`
- `nginx service unstable`

## Logs and Support

If something goes wrong:

1. Open `Help -> System Info`
2. Click `Copy Info`
3. Click `Open Log Folder`
4. Include the log file and copied info in the bug report
