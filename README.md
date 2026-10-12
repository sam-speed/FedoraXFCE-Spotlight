# Spotlight for Fedora XFCE

A lightweight, Alfred/Spotlight-style desktop launcher built with Python and Rofi for Fedora XFCE. It indexes and searches applications, files, and directories in a single unified list with predefined ranking rules.

---

## Requirements

To run this tool, ensure the following system packages are installed on your Fedora system:

* Python 3.6+
* Rofi
* XFCE4 Terminal
* Thunar / xdg-open
* libnotify (Optional)
* util-linux-user (Optional, for ionice)

### Package Installation Command

Run the following command in your terminal to install all required dependencies:

```bash
sudo dnf install -y python3 rofi xfce4-terminal thunar libnotify util-linux-user

```

---

## Configuration

You can customize the script behavior by editing the configuration section at the top of `spotlight.py`:

* `ARCHIVIO`: Path to a high-priority folder indexed without depth limits (e.g., `/srv/archivio/Archivio LB`).
* `ICONA_FILE`: Set to `"tipo"` for file-type-specific icons (PDF, image, video, etc.) or `"thunar"` for standard file manager icons.
* `ICON_THEME`: Set a custom icon theme (e.g., `"Papirus-Dark"`). Leave empty `""` to default to system settings.
* `RADICI`: Configures index roots, traversal depths, hidden file thresholds, and folder exclusion sets.

### Excluding Directories

At **line 50** in `spotlight.py`, you can modify the `ESCLUDI_HOME` set to add or remove folders that should be ignored during indexing:

```python
ESCLUDI_HOME = {
    ".cache", ".git", "node_modules", "__pycache__", ".venv", ".npm", ".cargo",
    ".rustup", ".var", ".mozilla", ".thunderbird", ".steam", ".wine", "flatpak",
    "Trash", ".Trash", "Cache", "GPUCache", "Code Cache", "CacheStorage",
}

```

* To exclude a folder, add its name to the set (e.g., `"Downloads"`).
* To include a folder, remove it from the set.

After modifying this list, force a re-index with `python3 spotlight.py --reindex`.

---

## Execution and Usage

### Manual Execution

* Launch search interface:
```bash
python3 spotlight.py

```


* Force re-indexing of the file system:
```bash
python3 spotlight.py --reindex

```



---

## Setting Up Keyboard Shortcut (Ctrl + Space)

### Step 1: Install the Script

Place the script inside your personal binary folder and grant execution permissions:

```bash
mkdir -p ~/.local/bin
mv spotlight.py ~/.local/bin/spotlight.py
chmod +x ~/.local/bin/spotlight.py

```

### Step 2: Bind Ctrl + Space Shortcut

You can set up the shortcut directly via terminal using `xfconf-query`:

```bash
xfconf-query -c xfce4-keyboard-shortcuts -p "/commands/custom/<Primary>space" -s "python3 /home/$USER/.local/bin/spotlight.py" --create -t string

```

Alternatively, you can configure it via GUI:

1. Open XFCE Application Menu -> Settings -> Keyboard.
2. Select the Application Shortcuts tab.
3. Click Add, enter `/home/$USER/.local/bin/spotlight.py` as the command.
4. Assign the key shortcut `Ctrl + Space`.

---

## Credits

Created with Claude Sonnet 5.6.
