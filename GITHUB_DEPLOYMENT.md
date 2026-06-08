# GitHub Deployment Notes

Recommended repository name:

```text
flex-sensor-agent-mcp
```

Recommended visibility:

```text
private
```

Private is recommended first because COMSOL models, local paths, and research
data can be sensitive. You can switch the GitHub repository to public later
after reviewing the content.

## Deployment Commands

From this folder:

```powershell
git init
git config user.email "1801874658@qq.com"
git config user.name "1801874658"
git add .
git commit -m "Package flexible pressure sensor Agent MCP"
```

Then create and push a GitHub repository:

```powershell
gh repo create flex-sensor-agent-mcp --private --source . --remote origin --push
```

If `gh` is not installed:

```powershell
winget install --id GitHub.cli -e
```

If `gh` is installed but not authenticated:

```powershell
gh auth login
```

After login, rerun:

```powershell
gh repo create flex-sensor-agent-mcp --private --source . --remote origin --push
```

