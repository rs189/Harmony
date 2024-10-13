# Harmony
 A looking-glass and libvirt integration for launching Windows applications with a native form factor.

# It is recommended to have a separate VM and Windows install when using Harmony as it is not designed to be used outside this project's scope.

## Requirements

* A functional libvirt domain.
* A functional looking glass installation.
* Python 3.10+ installation on both the host and the guest.

Optional:

* Install Microsoft PowerToys - Keyboard Manager to remap the Alt+Tab or other buttons inside the Windows guest to allow for more seamless integration with the host.
* Disable translucency effects in Windows.
* Disable UAC in Windows; otherwise, you will have to acknowledge the UAC prompt when the Harmony host tries to run an application.



## TODO:

* Live USB Host Device monitoring.
* Automatic suspend after a period of inactivity.
* Discord Rich Presence.
* Automatic GPU binding and unbinding in the host.

# Licence

This project is licensed under the MIT licence.