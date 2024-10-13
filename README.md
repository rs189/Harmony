# Harmony
 A looking-glass and libvirt integration for launching Windows applications with a native form factor.

https://github.com/rs189/Harmony/raw/refs/heads/main/demo.mp4

# It is recommended to have a separate VM and Windows install when using Harmony as it is not designed to be used outside this project's scope.

## Requirements

* A functional libvirt domain.
* A functional looking glass installation.
* Python 3.10+ installation on both the host and the guest.

## Installation

1. Copy the client folder into a desired location on the host; copy the host folder into a desired location on the guest (`C:\Program Files\Harmony Host` by default).
2. Install or copy Python 3.10+ into a folder called python inside the host installation location (`C:\Program Files\Harmony Host\python` by default).
3. Configure the `harmony.json` file to match your setup on both the host and the guest; keep in mind that your `looking-glass-port` would be `5900` and not `5905` unless configured otherwise.
4. Configure the `gpu-vms.json` of the client, specifying the domain names for your libvirt virtual machines.

5. Launch `listener.bat` to start the Harmony listener on the guest.
6. (Optional) Create a shortcut to the `listener.bat` file and copy it inside `shell:startup` folder for automatic startup on boot.
7. Create a `.json` configuration for your desired game inside the apps folder in the Harmony client folder, naming it without using spaces, following this example, `APPNAME.json` is created:

```
{
    "vm": "win10-games",
    "name": "Microsoft Flight Simulator",
    "splash": "msfs.png",
    "mainexe": "FlightSimulator.exe",
    "alwaysontop": true,
    "exes": [
        "FlightSimulator.exe"
    ],
    "killexes": [
        "explorer.exe",
        "taskmgr.exe",
        "msedge.exe",
        "msedgewebview2.exe"
    ],
    "usb_devices": [
        "Saitek PLC Saitek X52 PRO Flight Control System"
    ],
    "command": "steam://rungameid/1250410",
    "delay": 2,
    "timeout": 300
  }
  
```

You can obtain the Steam App ID from either SteamDB or by creating a shortcut using the Steam client and copying the launch options.

8. From inside the Harmony client folder, launch your desired game by either running the `env GDK_BACKEND=x11 /usr/bin/python app.py -app="APPNAME"` command in the terminal or create a `.desktop` naming it `com.harmony.msfs.APPNAME.desktop` where `APPNAME` follows the the name of the `.json` configuration, following this example:

```
[Desktop Entry]
Type=Application
Icon=/home/USERNAME/.icons/HarmonySur/msfs.png
Name=Microsoft Flight Simulator
Name[en]=Microsoft Flight Simulator
Name[en_GB]=Microsoft Flight Simulator
Name[en_GB.UTF-8]=Microsoft Flight Simulator
Exec=env GDK_BACKEND=x11 /usr/bin/python /home/USERNAME/Python/Harmony/client/app.py -app="APPNAME"
Hidden=false
NoDisplay=false
StartupNotify=true
Terminal=false
Categories=Game
```

Then copy the `.desktop` file created inside of `~/.local/share/applications`

9. (Optional) Install Microsoft PowerToys - Keyboard Manager to remap the Alt+Tab or other buttons inside the Windows guest to allow for more seamless integration with the host.
10. (Optional) Disable translucency effects in Windows.
11. (Optional) Disable UAC prompts in Windows; otherwise, you will have to acknowledge the UAC prompt when the Harmony host tries to run an application.

## TODO:

* Live USB Host Device monitoring.
* Automatic suspend after a period of inactivity.
* Discord Rich Presence.
* Automatic GPU binding and unbinding in the host.
* Simplified installation process

# Licence

This project is licensed under the MIT licence.