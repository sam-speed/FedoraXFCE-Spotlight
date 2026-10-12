# FedoraXFCE-Spotlight
A lightweight, Alfred/Spotlight-style desktop launcher built with Python and `rofi` for Fedora XFCE. It indexes and searches applications, files, and directories in a single unified list with predefined ranking rules.

---

## System Requirements

To run this tool, ensure the following system packages are installed on your Fedora system:

| Dependency | Purpose |
| :--- | :--- |
| **Python 3.6+** | Runtime environment for the script |
| **Rofi** | Graphical search window and interactive menu engine |
| **XFCE4 Terminal** | Required to launch terminal-based desktop apps |
| **Thunar / `xdg-open`** | File manager used to open selected directories and files |
| **`libnotify`** *(Optional)* | Enables system desktop notifications via `notify-send` |
| **`util-linux-user`** *(Optional)* | Provides `ionice` for background indexing priority management |

### Package Installation Command

Run the following command in your terminal to install all required dependencies:

```bash
sudo dnf install -y python3 rofi xfce4-terminal thunar libnotify util-linux-user
