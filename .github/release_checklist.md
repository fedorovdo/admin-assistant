# Release Checklist

Use this checklist before publishing a new GitHub Release.

## Versioning And Notes

- [ ] Bump the application version in the centralized version source
- [ ] Update `CHANGELOG.md`
- [ ] Review README and docs for any release-specific updates

## Validation

- [ ] Run the full test suite
- [ ] Smoke test the app from source if practical
- [ ] Verify About dialog version
- [ ] Verify System Info version

## Packaging

- [ ] Build the PyInstaller package
- [ ] Build the Windows installer
- [ ] Smoke test the installer on Windows
- [ ] Confirm the installed app starts correctly
- [ ] Confirm runtime logging and `%LOCALAPPDATA%\AdminAssistant` paths work

## Release Assets

- [ ] Confirm the installer filename is correct
- [ ] Attach the setup file to the GitHub Release
- [ ] Add release notes summary
