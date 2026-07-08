import sys
import os
import json
import shutil

from pathlib import Path
from PyQt6.QtGui import QFontDatabase, QFont

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QFileDialog, QLabel, 
                             QScrollArea, QSlider, QComboBox, QTableWidget,
                             QTableWidgetItem, QHeaderView, QSpinBox, QGroupBox,
                             QCheckBox, QTreeWidget, QTreeWidgetItem, QSplitter,
                             QLineEdit, QMessageBox, QProgressDialog, QKeySequenceEdit,
                             QFrame, QListWidget, QListWidgetItem, QToolTip, QSizePolicy, QDialog)
from PyQt6.QtCore import Qt, QTimer, QSize, QUrl, pyqtSignal, QEvent, QMimeData, QPoint
from PyQt6.QtGui import QIcon, QPixmap, QImage, QKeySequence, QShortcut, QDrag, QFont, QFontMetrics, QCursor

import cv2
import locale
import vlc

class Config:
    """Gestion de la configuration"""
    CONFIG_FILE = "Fitness_Viewer_config.json"
    
    @staticmethod
    def load():
        """Charge la configuration"""
        default_config = {
            "thumbnail_size": 200,
            "preview_resolution": "426x240",
            "volume": 50,
            "vertical_mode": False,
            "play_on_hover": True,
            "columns": 4,
            "last_folder": "",
            "target_folder": "",
            "copy_shortcut": "Ctrl+C",
            "show_quick_copy_buttons": False,            
            "last_active_folder": "",
            "last_include_subdirs": True,
            "last_root_files_only": False,
            "tooltip_font_size": 100,
            "view_mode": "thumbnails",
            "lazy_loading": True,
            "backup_destinations": [],
            "explorer_mode": "classic",
            "last_tag_filter": [("system", "all")],
            "last_valence_filter": "all",
            "last_target_browse_folder": "",
            "folder_fr": "",
            "folder_en": "",
            "active_source": "fr"
        }
        
        try:
            if os.path.exists(Config.CONFIG_FILE):
                with open(Config.CONFIG_FILE, 'r') as f:
                    loaded = json.load(f)
                    default_config.update(loaded)
        except:
            pass
            
        return default_config
    
    @staticmethod
    def save(config):
        """Sauvegarde la configuration"""
        try:
            with open(Config.CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=4)
            return True
        except:
            return False


class ClickableVideoWidget(QFrame):
    """Widget neutre pour le rendu VLC, cliquable pour pause/play."""
    clicked = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background-color: black;")
        # Indispensable pour que VLC obtienne un handle natif stable
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class InstantTooltip(QLabel):
    """Tooltip custom : affichage instantané, style cohérent, sans délai Qt"""
    _instance = None

    @classmethod
    def get(cls, app_widget):
        if cls._instance is None:
            cls._instance = cls(app_widget)
        return cls._instance

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.ToolTip |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self._current_pt = 10  # taille de base en points (100%)
        self._apply_style()
   
        self.hide()

    def _apply_style(self, pt=None):
        """Applique le stylesheet avec la taille de police pt (ou _current_pt par défaut)."""
        if pt is None:
            pt = self._current_pt
        self.setStyleSheet(f"""
            QLabel {{
                background-color: #2a2d3a;
                color: #e8eaf0;
                border: 1px solid #4a5270;
                border-radius: 6px;
                padding: 7px 11px;
                font-family: 'Segoe UI';
                font-size: {pt}pt;
            }}
        """)

    def update_font_size(self, pct):
        """Met à jour la taille de base en pourcentage (utilisé par l'app)."""
        self._current_pt = max(6, round(10 * pct / 100))
        self._apply_style()

    def show_at(self, text, global_pos, nowrap=False, font_size=None):
            self.setText(text)
            self.setWordWrap(False)

            # Appliquer une taille ponctuelle si demandée, sinon garder la taille courante
            if font_size is not None:
                self.setStyleSheet(f"""
                    QLabel {{
                        background-color: #2a2d3a;
                        color: #e8eaf0;
                        border: 1px solid #4a5270;
                        border-radius: 6px;
                        padding: 7px 11px;
                        font-family: 'Segoe UI';
                        font-size: {font_size}pt;
                    }}
                """)
            else:
                self._apply_style()
            
            # Calculer la largeur naturelle du texte
            fm = self.fontMetrics()
            lines = text.split("\n")
            natural_w = max(fm.horizontalAdvance(line) for line in lines) + 35  # 35 = padding L+R
            capped_w = min(natural_w, 700)  # max 700px
            self.setFixedWidth(capped_w)
            self.setWordWrap(natural_w > 700)  # wrap seulement si vraiment trop long
            self.adjustSize()

            screen = QApplication.primaryScreen().geometry()
            x = global_pos.x() + 14
            y = global_pos.y() + 20
            if x + self.width() > screen.right() - 10:
                x = global_pos.x() - self.width() - 4
            if y + self.height() > screen.bottom() - 10:
                y = global_pos.y() - self.height() - 4
            self.move(x, y)
            self.show()
            self.raise_()

    def hide_tip(self):
        self._apply_style()   # restaure la taille normale pour les prochains affichages
        self.hide()


class StatusBar(QFrame):
    """Barre de statut personnalisée avec fond coloré"""
    def __init__(self):
        super().__init__()
        self.setup_ui()
        
    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 5, 15, 5)
        layout.setSpacing(0)

        # Spacer gauche
        layout.addStretch(1)

        # Icône collée au texte
        self.icon_label = QLabel("")
        self.icon_label.setFixedWidth(20)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_label)

        layout.addSpacing(6)

        # Message
        self.message_label = QLabel("Prêt")
        self.message_label.setStyleSheet("color: #cccccc; font-size: 12px;")
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.message_label)

        # Spacer droit (équilibré avec le gauche pour centrer le groupe)
        layout.addStretch(1)

        # Bouton d'information des dépendances à droite
        self.info_button = QPushButton()
        self.info_button.setFixedSize(28, 28)
        self.info_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.info_button.setToolTip("Afficher les dépendances")
        self.info_button.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
            }
        """)
        layout.addWidget(self.info_button)

        self.setFixedHeight(32)
        self.set_neutral()
    
    def set_info_icon(self, icon_pixmap, tooltip_text):
        """Configure l'icône d'information à droite avec son tooltip instantané."""
        if icon_pixmap:
            self.info_label.setPixmap(icon_pixmap.scaled(
                20, 20,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))

        def _enter(event):
            InstantTooltip.get(self).show_at(tooltip_text, event.globalPosition().toPoint(), nowrap=True)

        def _leave(event):
            InstantTooltip.get(self).hide_tip()

        self.info_label.enterEvent = _enter
        self.info_label.leaveEvent = _leave

    def set_success(self, message):
        self.setStyleSheet("background-color: #2a2a2a; border-radius: 4px;")
        self.icon_label.setText("✅")
        self.message_label.setText(message)
        self.message_label.setStyleSheet("color: #dddddd; font-size: 12px;")

    def set_error(self, message):
        self.setStyleSheet("background-color: #2a2a2a; border-radius: 4px;")
        self.icon_label.setText("❌")
        self.message_label.setText(message)
        self.message_label.setStyleSheet("color: #dddddd; font-size: 12px;")

    def set_info(self, message):
        self.setStyleSheet("background-color: #2a2a2a; border-radius: 4px;")
        self.icon_label.setText("ℹ️")
        self.message_label.setText(message)
        self.message_label.setStyleSheet("color: #dddddd; font-size: 12px;")

    def set_warning(self, message):
        self.setStyleSheet("background-color: #2a2a2a; border-radius: 4px;")
        self.icon_label.setText("⚠️")
        self.message_label.setText(message)
        self.message_label.setStyleSheet("color: #dddddd; font-size: 12px;")

    def set_neutral(self):
        self.setStyleSheet("background-color: #2a2a2a; border-radius: 4px;")
        self.icon_label.setText("🎬")
        self.message_label.setText("Prêt - Sélectionnez un dossier source pour commencer")
        self.message_label.setStyleSheet("color: #aaaaaa; font-size: 12px;")


class VideoThumbnailContainer(QWidget):
    """Conteneur pour une vignette vidéo + bouton de copie rapide optionnel"""
    def __init__(self, video_path, thumbnail_size, parent_viewer):
        super().__init__()
        self.video_path = video_path
        self.parent_viewer = parent_viewer
        self.thumbnail_size = thumbnail_size

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # /!\ NOTE: Utilise bien la version asynchrone de VideoThumbnail ici
        self.thumbnail = VideoThumbnail(video_path, thumbnail_size, parent_viewer)
        layout.addWidget(self.thumbnail)
        # Initialiser l'arrondi des coins inférieurs en fonction de la visibilité du bouton
        self.thumbnail.set_bottom_rounded(not parent_viewer.show_quick_copy_buttons)

        self.save_badge = None

        self.norm_badge = QLabel("", self.thumbnail)
        self.norm_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.norm_badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.norm_badge.setStyleSheet("""
            QLabel {
                background-color: rgba(80, 40, 120, 210);
                color: #e8d8ff;
                font-size: 9px;
                font-weight: bold;
                border: 1px solid #a070e0;
                border-radius: 6px;
                padding: 2px 6px;
            }
        """)
        self.norm_badge.hide()
        self.norm_badge.raise_()

        # --- NOUVEAU : Widget pour le badge de backup en carré ---
        self.backup_indicator = QLabel("B", self.thumbnail)
        self.backup_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.backup_indicator.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.backup_indicator.hide()
        # ---------------------------------------------------------
        

        self._refresh_norm_badge()

        self.quick_copy_btn = QPushButton("⏶")
        self.quick_copy_btn.setToolTip("Copier vers la cible")
        self.quick_copy_btn.setFixedHeight(16)
        self.quick_copy_btn.setFixedWidth(thumbnail_size)
        self.quick_copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.quick_copy_btn.setStyleSheet("""
            QPushButton {
                background-color: #444;
                color: #aaa;
                border: 1px solid #555;
                border-top: none;
                border-top-left-radius: 0px;
                border-top-right-radius: 0px;
                border-bottom-left-radius: 4px;
                border-bottom-right-radius: 4px;
                padding: 0px 4px;
                font-size: 9px;
            }
            QPushButton:hover { background-color: #5a5a5a; color: white; }
        """)
        self.quick_copy_btn.clicked.connect(self.quick_copy)

        # Tooltip du bouton
        def _quick_copy_enter(event):
            InstantTooltip.get(self.parent_viewer).show_at("Copier vers la cible", event.globalPosition().toPoint())
        def _quick_copy_leave(event):
            InstantTooltip.get(self.parent_viewer).hide_tip()

        self.quick_copy_btn.enterEvent = _quick_copy_enter
        self.quick_copy_btn.leaveEvent = _quick_copy_leave
        self.quick_copy_btn.setToolTip("")

        layout.addWidget(self.quick_copy_btn)
        self.quick_copy_btn.setVisible(parent_viewer.show_quick_copy_buttons)

    def _norm_badge_size(self):
        font = QFont()
        font.setPixelSize(9)
        font.setBold(True)
        fm = QFontMetrics(font)
        text_w = fm.horizontalAdvance(self.norm_badge.text())
        text_h = fm.ascent() + fm.descent()
        return max(text_w + 14, 20), max(text_h + 6, 14)

    def _reposition_norm_badge(self):
        thumb_w = self.thumbnail_size
        thumb_h = int(self.thumbnail_size * 3 / 4)
        
        # On commence l'alignement depuis le bord droit (marge de 5px)
        current_x = thumb_w - 5
        
        # On récupère la hauteur de référence calculée par l'application
        _, nh = self._norm_badge_size()
        
        # 1. Placement de la pastille de normalisation (si visible)
        if hasattr(self, 'norm_badge') and self.norm_badge.isVisible():
            nw, _ = self._norm_badge_size()
            current_x -= nw
            self.norm_badge.setGeometry(current_x, thumb_h - nh - 5, nw, nh)
            current_x -= 4  # Espacement de séparation entre les deux badges
            
        # 2. Placement du carré de backup "B" (si visible)
        if hasattr(self, 'backup_indicator') and self.backup_indicator.isVisible():
            bw = nh  # Carré parfait : la largeur est identique à la hauteur du badge
            current_x -= bw
            self.backup_indicator.setGeometry(current_x, thumb_h - nh - 5, bw, nh)

    def _refresh_norm_badge(self):
        if os.path.splitext(self.video_path)[1].lower() in self.parent_viewer.image_extensions:
            return
        
        info = self.parent_viewer._get_norm_info(self.video_path)
        
        # 1. Rafraîchissement de la pastille de normalisation
        if info:
            preset = info.get("preset", "")
            self.norm_badge.setText(preset)
            colors = {
                "Standard":  ("rgba(30, 80, 160, 220)", "#7ab8ff", "#5090d0"),
                "Dynamique": ("rgba(140, 80, 0, 220)",  "#ffd070", "#c09030"),
                "Percutant": ("rgba(160, 30, 30, 220)", "#ff9090", "#c05050"),
            }
            bg, fg, border = colors.get(preset, ("rgba(80, 40, 120, 210)", "#e8d8ff", "#a070e0"))
            self.norm_badge.setStyleSheet(f"QLabel {{ background-color: {bg}; color: {fg}; font-size: 9px; font-weight: bold; border: 1px solid {border}; border-radius: 6px; padding: 2px 6px; }}")
            self.norm_badge.show()
        else:
            self.norm_badge.hide()
            # Teinte bleutée par défaut (style interface) si aucun preset n'est affiché
            bg, fg, border = "rgba(30, 80, 160, 220)", "#7ab8ff", "#5090d0"

        # 2. Rafraîchissement du badge de Backup "B"
        backup_dir = os.path.join(os.path.dirname(self.video_path), ".normalized_backup")
        backup_path = os.path.join(backup_dir, os.path.basename(self.video_path))
        
        if os.path.exists(backup_path):
            # Style identique à l'étiquette, padding nul pour un centrage parfait du caractère dans son carré
            self.backup_indicator.setStyleSheet(f"""
                QLabel {{
                    background-color: {bg};
                    color: {fg};
                    font-size: 9px;
                    font-weight: bold;
                    border: 1px solid {border};
                    border-radius: 6px;
                    padding: 0px;
                }}
            """)
            self.backup_indicator.show()
            self.backup_indicator.raise_()
        else:
            self.backup_indicator.hide()

        # 3. Lancement du repositionnement géométrique
        self._reposition_norm_badge()


    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._reposition_norm_badge)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_norm_badge()
        if hasattr(self, 'video_image_label'):
            self.video_image_label.setGeometry(0, 0, self.video_widget.width(), self.video_widget.height())

    def quick_copy(self):
        self.parent_viewer.deselect_all_thumbnails()
        self.thumbnail.is_selected = True
        self.thumbnail.update_style()
        self.parent_viewer.current_selected_video = self.video_path
        self.parent_viewer.update_copy_button_state()
        self.parent_viewer.copy_to_target()

    def set_quick_copy_visible(self, visible):
        self.quick_copy_btn.setVisible(visible)
        # Mettre à jour l'arrondi des coins inférieurs : si bouton masqué, arrondi
        self.thumbnail.set_bottom_rounded(not visible)

    # NOUVEAU : C'est le conteneur qui intercepte et applique la logique globale de l'application !
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            ctrl_pressed = event.modifiers() & Qt.KeyboardModifier.ControlModifier
            in_management = self.parent_viewer.management_mode
            in_tags_view = self.parent_viewer.explorer_mode == "tags"

            if in_management and in_tags_view:
                if ctrl_pressed:
                    self.thumbnail.is_selected = not self.thumbnail.is_selected
                    self.thumbnail.update_style()
                    if self.thumbnail.is_selected:
                        self.parent_viewer.current_selected_video = self.video_path
                    else:
                        if self.parent_viewer.current_selected_video == self.video_path:
                            self.parent_viewer.current_selected_video = None
                else:
                    if not self.thumbnail.is_selected:
                        self.parent_viewer.deselect_all_thumbnails()
                        self.thumbnail.is_selected = True
                        self.thumbnail.update_style()
                        self.parent_viewer.current_selected_video = self.video_path
            else:
                # Comportement standard : sélection exclusive
                self.parent_viewer.deselect_all_thumbnails()
                self.thumbnail.is_selected = True
                self.thumbnail.update_style()
                self.parent_viewer.current_selected_video = self.video_path

            # Met à jour l'activation du bouton de copie principal
            self.parent_viewer.update_copy_button_state()
            self.thumbnail.drag_start_position = event.pos()

            # Lancement de la lecture si le survol est désactivé (et hors mode gestion)
            if not self.parent_viewer.play_on_hover and not in_management:
                self.parent_viewer.play_preview(self.video_path)

        elif event.button() == Qt.MouseButton.RightButton:
            if self.parent_viewer.management_mode and self.parent_viewer.explorer_mode == "tags":
                if not self.thumbnail.is_selected:
                    self.parent_viewer.deselect_all_thumbnails()
                    self.thumbnail.is_selected = True
                    self.thumbnail.update_style()
                    self.parent_viewer.current_selected_video = self.video_path
                self.thumbnail._show_tag_removal_popup(event.globalPosition().toPoint())
            else:
                self.thumbnail._show_context_menu(event.globalPosition().toPoint())


from PyQt6.QtCore import QRunnable, QThreadPool, QObject, pyqtSignal
import hashlib

class ThumbnailSignals(QObject):
    """Signaux pour communiquer entre le thread secondaire et l'interface principale"""
    done = pyqtSignal(str, QImage, str)  # renvoie : video_path, q_image, tooltip_text
    error = pyqtSignal(str, str)         # renvoie : video_path, error_msg


class ThumbnailWorker(QRunnable):
    """Worker chargé d'extraire ou de charger la vignette en arrière-plan"""
    def __init__(self, video_path, thumbnail_size, cache_dir):
        super().__init__()
        self.video_path = video_path
        self.thumbnail_size = thumbnail_size
        self.cache_dir = cache_dir
        self.signals = ThumbnailSignals()

    def run(self):
        try:
            # 1. Générer une clé unique pour cette vidéo basée sur son chemin absolu
            video_hash = hashlib.md5(self.video_path.encode('utf-8')).hexdigest()
            cache_path = os.path.join(self.cache_dir, f"{video_hash}.jpg")
            
            frame_rgb = None
            raw_name = os.path.splitext(os.path.basename(self.video_path))[0]
            tooltip_text = raw_name.split(" - ", 1)[1].strip() if " - " in raw_name else raw_name

            # 2. Tenter de lire l'image depuis le cache disque
            if os.path.exists(cache_path):
                frame_bgr = cv2.imread(cache_path)
                if frame_bgr is not None:
                    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

            # 3. Si non présente dans le cache, on l'extrait via OpenCV
            if frame_rgb is None:
                cap = cv2.VideoCapture(self.video_path)
                ret, frame = cap.read()
                cap.release()
                
                if ret:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    # Sauvegarde immédiate dans le cache au format natif BGR d'OpenCV
                    os.makedirs(self.cache_dir, exist_ok=True)
                    cv2.imwrite(cache_path, frame)
                else:
                    self.signals.error.emit(self.video_path, "❌")
                    return

            # 4. Conversion en QImage de manière thread-safe
            h, w, ch = frame_rgb.shape
            bytes_per_line = ch * w
            
            # /!\ CRUCIAL : Le .copy() détache le buffer mémoire du tableau numpy global du thread.
            # Sans lui, la mémoire serait nettoyée à la fin de run() provoquant un crash de l'UI.
            q_img = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
            
            # Émettre l'image prête vers le thread principal
            self.signals.done.emit(self.video_path, q_img, tooltip_text)

        except Exception as e:
            self.signals.error.emit(self.video_path, f"⚠️ Erreur: {str(e)}")


class VideoThumbnail(QLabel):
    """Widget asynchrone qui charge sa vignette en tâche de fond et transmet ses clics au parent"""
    CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cineblast_thumbnails")
    loaded_signal = pyqtSignal()

    def __init__(self, video_path, thumbnail_size, parent_viewer):
        super().__init__()
        self.video_path = video_path
        self.parent_viewer = parent_viewer
        self.thumbnail_size = thumbnail_size
        self.is_selected = False
        self.drag_start_position = None
        self._tooltip_text = ""
        self.bottom_rounded = False  # Par défaut, coins inférieurs plats

        self.update_style()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setScaledContents(False)
        self._apply_fixed_size()
        self.setToolTip("")
        self.setMouseTracking(True)
        
        # Déclenchement asynchrone
        self.start_thumbnail_loading()

        # Détecter si c'est une image
        ext = os.path.splitext(video_path)[1].lower()
        if ext in self.parent_viewer.image_extensions:
            self._load_image()
        else:
            self.start_thumbnail_loading()

    def _load_image(self):
        """Charge et affiche une image directement."""
        try:
            pixmap = QPixmap(self.video_path)
            if pixmap.isNull():
                self.setText("❌")
                self._tooltip_text = "Image invalide"
                return
            box_w = self.thumbnail_size
            box_h = int(self.thumbnail_size * 3 / 4)
            scaled_pixmap = pixmap.scaled(box_w, box_h,
                                         Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation)
            self.setPixmap(scaled_pixmap)
            self._tooltip_text = os.path.splitext(os.path.basename(self.video_path))[0]
            self.loaded_signal.emit()
        except Exception as e:
            self.setText("⚠️")
            self._tooltip_text = f"Erreur: {str(e)}"

    def _apply_fixed_size(self):
        w = self.thumbnail_size
        h = int(self.thumbnail_size * 3 / 4)
        self.setFixedSize(w, h)
        
    def update_style(self):
        border_color = "#0078d4" if self.is_selected else "#555"
        if self.bottom_rounded:
            bottom_radius = "5px"
        else:
            bottom_radius = "0px"
        self.setStyleSheet(f"""
            QLabel {{
                border: 1px solid {border_color};
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                border-bottom-left-radius: {bottom_radius};
                border-bottom-right-radius: {bottom_radius};
                padding: 5px;
                background-color: #2b2b2b;
            }}
            QLabel:hover {{ border: 1px solid #1084d8; }}
        """)

    def set_bottom_rounded(self, rounded):
        """Définit si les coins inférieurs sont arrondis."""
        self.bottom_rounded = rounded
        self.update_style()

    def start_thumbnail_loading(self):
        self.setText("⌛")
        worker = ThumbnailWorker(self.video_path, self.thumbnail_size, self.CACHE_DIR)
        worker.signals.done.connect(self.on_thumbnail_loaded)
        worker.signals.error.connect(self.on_thumbnail_error)
        QThreadPool.globalInstance().start(worker)

    def on_thumbnail_loaded(self, video_path, q_img, tooltip_text):
        if video_path != self.video_path:
            return
        pixmap = QPixmap.fromImage(q_img)
        box_w = self.thumbnail_size
        box_h = int(self.thumbnail_size * 3 / 4)
        scaled_pixmap = pixmap.scaled(box_w, box_h,
                                     Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
        self.setPixmap(scaled_pixmap)
        self._tooltip_text = tooltip_text
        self.loaded_signal.emit()
        
        if self.parent() and hasattr(self.parent(), '_reposition_norm_badge'):
            self.parent()._reposition_norm_badge()

    def on_thumbnail_error(self, video_path, error_msg):
        if video_path != self.video_path:
            return
        if error_msg.startswith("⚠️"):
            self.setText("⚠️")
            self._tooltip_text = error_msg
        else:
            self.setText(error_msg)
            self._tooltip_text = os.path.splitext(os.path.basename(video_path))[0]
        self.loaded_signal.emit()

    def enterEvent(self, event):
        tip_text = self._tooltip_text
        ds = getattr(self.parent_viewer, '_data_store', None)
        if ds:
            tags = ds.get_tags(self.video_path)
            if tags:
                tip_text = tip_text + "\n🏷 " + "  ".join(tags) if tip_text else "🏷 " + "  ".join(tags)
        if tip_text:
            InstantTooltip.get(self.parent_viewer).show_at(tip_text, event.globalPosition().toPoint())
        if self.parent_viewer.play_on_hover and not self.parent_viewer.management_mode:
            self.parent_viewer.play_preview(self.video_path)
        super().enterEvent(event)

    def leaveEvent(self, event):
        InstantTooltip.get(self.parent_viewer).hide_tip()
        super().leaveEvent(event)

    # Transfert direct et propre vers le conteneur parent
    def mousePressEvent(self, event):
        if self.parent():
            self.parent().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # La logique de Drag (QMimeData) utilise self.drag_start_position
        if self.parent_viewer.management_mode and event.buttons() & Qt.MouseButton.LeftButton:
            if self.drag_start_position is not None:
                if (event.pos() - self.drag_start_position).manhattanLength() >= QApplication.startDragDistance():
                    self._execute_drag()
                    return
        super().mouseMoveEvent(event)

    def _execute_drag(self):
        drag = QDrag(self)
        mime_data = QMimeData()
        selected_paths = self.parent_viewer._get_selected_video_paths()
        if not selected_paths:
            selected_paths = [self.video_path]

        mime_data.setText("||".join(selected_paths))
        mime_data.setData("application/x-videopath-list", "\n".join(selected_paths).encode('utf-8'))
        if len(selected_paths) == 1:
            mime_data.setData("application/x-videopath", selected_paths[0].encode('utf-8'))

        if self.pixmap():
            base_pixmap = self.pixmap().scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio)
        else:
            base_pixmap = QPixmap(100, 100)
            base_pixmap.fill(Qt.GlobalColor.darkGray)

        drag.setMimeData(mime_data)
        drag.setPixmap(base_pixmap)
        drag.exec(Qt.DropAction.MoveAction)

    def _show_context_menu(self, global_pos):
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #2a2d3a; color: #e8eaf0; border: 1px solid #4a5270; border-radius: 6px; }")
        act_rename = menu.addAction("✏️  Renommer")
        menu.addSeparator()
        act_delete = menu.addAction("🗑️  Supprimer")
        action = menu.exec(global_pos)
        if action == act_rename:
            self.parent_viewer.rename_file(self.video_path)
        elif action == act_delete:
            self.parent_viewer.trash_file(self.video_path)

    def _show_tag_removal_popup(self, global_pos):
        # ... (Garde ton code d'origine de _show_tag_removal_popup ici sans changement)
        pass

class VideoTableRow(QWidget):
    """Widget pour une ligne de tableau en mode détails"""

    TRUEPEAK_WARN  = -3.0
    TRUEPEAK_ERROR = -1.0
    LUFS_WARN_LOW  = -23.0
    LUFS_ERROR_LOW = -35.0
    LUFS_WARN_HIGH = -14.0
    LUFS_ERROR_HIGH = -9.0

    COL_CHECK_W = 28
    COL_TYPE_W  = 82
    COL_DATE_W  = 120
    COL_PEAK_W  = 90
    COL_LUFS_W  = 90

    # Couleurs des presets de normalisation
    PRESET_COLORS = {
        "Standard":  "#4a9adf",
        "Dynamique": "#e0a020",
        "Percutant": "#e04040",
    }

    def __init__(self, video_path, parent_viewer):
        super().__init__()
        self.video_path = video_path
        self.parent_viewer = parent_viewer
        self.is_selected = False
        self.setMouseTracking(True)
        self.setup_ui()
        self._refresh_audio_display()
        self._refresh_norm_display()

    def setup_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(0)

        self.check_box = QCheckBox()
        self.check_box.setFixedWidth(self.COL_CHECK_W)
        self.check_box.setToolTip(
            "Cocher pour forcer la ré-analyse de ce fichier\n"
            "Si aucune case n'est cochée : analyse tous les fichiers non encore analysés"
        )
        self.check_box.setStyleSheet("""
            QCheckBox { margin-left: 4px; }
            QCheckBox::indicator {
                width: 17px; height: 17px;
                border-radius: 4px;
            }
            QCheckBox::indicator:unchecked {
                border: 2px solid #777;
                background: #1e1e1e;
                border-radius: 4px;
            }
            QCheckBox::indicator:unchecked:hover {
                border: 2px solid #0078d4;
                background: #1a2a3a;
            }
            QCheckBox::indicator:checked {
                border: 2px solid #0078d4;
                background-color: #0078d4;
                border-radius: 4px;
                image: url(none);
            }
            QCheckBox::indicator:checked:hover {
                border: 2px solid #40a0ff;
                background-color: #1084d8;
            }
        """)
        self.check_box.stateChanged.connect(self._on_check_changed)
        layout.addWidget(self.check_box)

        sep0 = QFrame()
        sep0.setFrameShape(QFrame.Shape.VLine)
        sep0.setStyleSheet("QFrame { color: #444; }")
        layout.addWidget(sep0)

        filename = os.path.basename(self.video_path)
        size_mb = os.path.getsize(self.video_path) / (1024 * 1024)

        self.label = QLabel(f"{filename}  ({size_mb:.2f} MB)")
        self.label.setStyleSheet("padding: 5px 8px; color: white;")
        self.label.setMinimumWidth(0)
        self.label.setSizePolicy(
            self.label.sizePolicy().horizontalPolicy(),
            self.label.sizePolicy().verticalPolicy()
        )
        from PyQt6.QtWidgets import QSizePolicy as _QSP
        self.label.setSizePolicy(_QSP.Policy.Ignored, _QSP.Policy.Preferred)
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self._full_label_text = f"{filename}  ({size_mb:.2f} MB)"
        layout.addWidget(self.label, stretch=1)

        sep_type = QFrame()
        sep_type.setFrameShape(QFrame.Shape.VLine)
        sep_type.setStyleSheet("QFrame { color: #444; }")
        layout.addWidget(sep_type)

        self.lbl_type = QLabel("")
        self.lbl_type.setFixedWidth(self.COL_TYPE_W)
        self.lbl_type.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_type.setStyleSheet("padding: 5px 4px; color: #888; font-size: 10px;")
        layout.addWidget(self.lbl_type)

        sep_date = QFrame()
        sep_date.setFrameShape(QFrame.Shape.VLine)
        sep_date.setStyleSheet("QFrame { color: #444; }")
        layout.addWidget(sep_date)

        self.lbl_date = QLabel("")
        self.lbl_date.setFixedWidth(self.COL_DATE_W)
        self.lbl_date.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_date.setStyleSheet("padding: 5px 4px; color: #888; font-size: 10px;")
        layout.addWidget(self.lbl_date)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet("QFrame { color: #444; }")
        layout.addWidget(sep1)

        self.lbl_peak = QLabel("…")
        self.lbl_peak.setFixedWidth(self.COL_PEAK_W)
        self.lbl_peak.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_peak.setStyleSheet("padding: 5px 4px; color: #888;")
        layout.addWidget(self.lbl_peak)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setStyleSheet("QFrame { color: #444; }")
        layout.addWidget(sep2)

        self.lbl_lufs = QLabel("…")
        self.lbl_lufs.setFixedWidth(self.COL_LUFS_W)
        self.lbl_lufs.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_lufs.setStyleSheet("padding: 5px 4px; color: #888;")
        layout.addWidget(self.lbl_lufs)

        self.setLayout(layout)
        self.update_style()

    def _refresh_norm_display(self):
        """Met à jour les colonnes Type et Date depuis l'historique de normalisation."""
        info = self.parent_viewer._get_norm_info(self.video_path)
        if info:
            preset = info.get("preset", "")
            date_str = info.get("date", "")
            color = self.PRESET_COLORS.get(preset, "#aaa")
            self.lbl_type.setText(preset)
            self.lbl_type.setStyleSheet(
                f"padding: 5px 4px; color: {color}; font-size: 10px; font-weight: bold;"
            )
            self.lbl_date.setText(date_str)
            self.lbl_date.setStyleSheet("padding: 5px 4px; color: #aaa; font-size: 10px;")
        else:
            self.lbl_type.setText("")
            self.lbl_type.setStyleSheet("padding: 5px 4px; color: #888; font-size: 10px;")
            self.lbl_date.setText("")
            self.lbl_date.setStyleSheet("padding: 5px 4px; color: #888; font-size: 10px;")

    def _on_check_changed(self, state):
        self.update_style()

    def is_checked(self):
        return self.check_box.isChecked()

    def set_checked(self, value: bool):
        self.check_box.blockSignals(True)
        self.check_box.setChecked(value)
        self.check_box.blockSignals(False)
        self.update_style()

    def _refresh_audio_display(self):
        data = self.parent_viewer._get_audio_cache(self.video_path)
        norm_info = self.parent_viewer._get_norm_info(self.video_path)

        if data is None:
            self.lbl_peak.setText("…")
            self.lbl_peak.setStyleSheet("padding: 5px 4px; color: #888;")
            self.lbl_lufs.setText("…")
            self.lbl_lufs.setStyleSheet("padding: 5px 4px; color: #888;")
            return
        if data == "error":
            self.lbl_peak.setText("N/A")
            self.lbl_peak.setStyleSheet("padding: 5px 4px; color: #666;")
            self.lbl_lufs.setText("N/A")
            self.lbl_lufs.setStyleSheet("padding: 5px 4px; color: #666;")
            return

        tp   = data.get("true_peak")
        lufs = data.get("lufs")
        pre_tp   = norm_info.get("pre_tp")   if isinstance(norm_info, dict) else None
        pre_lufs = norm_info.get("pre_lufs") if isinstance(norm_info, dict) else None

        # -- True Peak ----------------------------------------------------
        if tp is not None:
            peak_color = self._peak_color(tp)
            fw = "bold" if peak_color != "white" else "normal"
            if pre_tp is not None:
                html = (
                    f'<span style="color:{peak_color}; font-weight:{fw};">{tp:+.1f} dBTP</span>'
                    f'<br><span style="color:#666; font-size:8pt;">{pre_tp:+.1f} dBTP</span>'
                )
                self.lbl_peak.setTextFormat(Qt.TextFormat.RichText)
                self.lbl_peak.setText(html)
            else:
                self.lbl_peak.setTextFormat(Qt.TextFormat.PlainText)
                self.lbl_peak.setText(f"{tp:+.1f} dBTP")
            self.lbl_peak.setStyleSheet(f"padding: 2px 4px; color: {peak_color};")
        else:
            self.lbl_peak.setTextFormat(Qt.TextFormat.PlainText)
            self.lbl_peak.setText("N/A")
            self.lbl_peak.setStyleSheet("padding: 5px 4px; color: #666;")

        # -- LUFS ---------------------------------------------------------
        if lufs is not None:
            lufs_color = self._lufs_color(lufs)
            fw = "bold" if lufs_color != "white" else "normal"
            if pre_lufs is not None:
                html = (
                    f'<span style="color:{lufs_color}; font-weight:{fw};">{lufs:.1f} LUFS</span>'
                    f'<br><span style="color:#666; font-size:8pt;">{pre_lufs:.1f} LUFS</span>'
                )
                self.lbl_lufs.setTextFormat(Qt.TextFormat.RichText)
                self.lbl_lufs.setText(html)
            else:
                self.lbl_lufs.setTextFormat(Qt.TextFormat.PlainText)
                self.lbl_lufs.setText(f"{lufs:.1f} LUFS")
            self.lbl_lufs.setStyleSheet(f"padding: 2px 4px; color: {lufs_color};")
        else:
            self.lbl_lufs.setTextFormat(Qt.TextFormat.PlainText)
            self.lbl_lufs.setText("N/A")
            self.lbl_lufs.setStyleSheet("padding: 5px 4px; color: #666;")

    def _peak_color(self, tp):
        if tp > self.TRUEPEAK_ERROR:
            return "#ff4444"
        if tp > self.TRUEPEAK_WARN:
            return "#ff9900"
        return "white"

    def _lufs_color(self, lufs):
        if lufs > self.LUFS_ERROR_HIGH or lufs < self.LUFS_ERROR_LOW:
            return "#ff4444"
        if lufs > self.LUFS_WARN_HIGH or lufs < self.LUFS_WARN_LOW:
            return "#ff9900"
        return "white"

    def update_style(self):
        if self.is_selected:
            bg = "#3b5a7a"
        elif self.check_box.isChecked():
            bg = "#2a3a2a"
        else:
            bg = "#2b2b2b"
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {bg};
                border-bottom: 1px solid #444;
            }}
            QWidget:hover {{
                background-color: #353535;
            }}
        """)

    def _elide_label(self):
        """Élide le texte du label nom de fichier selon la largeur disponible."""
        if not hasattr(self, '_full_label_text'):
            return
        fm = QFontMetrics(self.label.font())
        available = self.label.width() - 16  # soustraire le padding
        if available > 10:
            elided = fm.elidedText(
                self._full_label_text,
                Qt.TextElideMode.ElideRight,
                available
            )
            self.label.setText(elided)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide_label()

    def enterEvent(self, event):
        # Afficher le nom complet via InstantTooltip si le texte est élidé
        if hasattr(self, '_full_label_text') and self.label.text() != self._full_label_text:
            tip = InstantTooltip.get(self.parent_viewer)
            tip.show_at(self._full_label_text, event.globalPosition().toPoint())
        if self.parent_viewer.play_on_hover and not self.parent_viewer.management_mode:
            self.parent_viewer.play_preview(self.video_path)
        super().enterEvent(event)

    def leaveEvent(self, event):
        InstantTooltip.get(self.parent_viewer).hide_tip()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # -- Détecter si le clic est dans la zone checkbox ----------------
            check_rect = self.check_box.geometry()
            in_check_zone = check_rect.contains(event.pos())
            if in_check_zone:
                # Shift+clic : sélection de plage
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self.parent_viewer._shift_click_check(self)
                    return
                # Clic simple : bascule l'état, mémorise la position, démarre le drag
                new_state = not self.check_box.isChecked()
                self.set_checked(new_state)
                # Mémoriser l'index pour un éventuel Shift+clic ultérieur
                try:
                    self.parent_viewer._last_checked_idx = \
                        self.parent_viewer.row_widgets.index(self)
                except ValueError:
                    pass
                self.parent_viewer._drag_check_active = True
                self.parent_viewer._drag_check_state  = new_state
                self.parent_viewer._drag_check_last   = self
                return
            # -- Clic sur le reste de la ligne ----------------------------
            self.parent_viewer.deselect_all_rows()
            self.is_selected = True
            self.update_style()
            self.parent_viewer.current_selected_video = self.video_path
            if not self.parent_viewer.play_on_hover and not self.parent_viewer.management_mode:
                self.parent_viewer.play_preview(self.video_path)

        elif event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())

        super().mousePressEvent(event)

    def _show_context_menu(self, global_pos):
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2a2d3a;
                color: #e8eaf0;
                border: 1px solid #4a5270;
                border-radius: 6px;
                padding: 4px 0px;
            }
            QMenu::item {
                padding: 6px 20px 6px 16px;
                border-radius: 4px;
                margin: 2px 4px;
            }
            QMenu::item:selected {
                background-color: #0078d4;
                color: white;
            }
        """)
        act_rename = menu.addAction("✏️  Renommer")
        menu.addSeparator()
        act_delete = menu.addAction("🗑️  Supprimer")
        action = menu.exec(global_pos)
        if action == act_rename:
            self.parent_viewer.rename_file(self.video_path)
        elif action == act_delete:
            self.parent_viewer.trash_file(self.video_path)


class FolderTreeWidget(QTreeWidget):
    """Widget arbre pour naviguer dans les dossiers"""
    def __init__(self, parent_viewer):
        super().__init__()
        self.parent_viewer = parent_viewer
        self.sort_ascending = True
        self.setHeaderLabel("📁 Dossiers")
        self.itemClicked.connect(self.on_item_clicked)
        self.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setMouseTracking(True)

        self.setStyleSheet("""
            QTreeWidget {
                background-color: #1e1e1e;
                color: white;
                border: none;
            }
            QTreeWidget::item { 
                height: 22px;
                padding: 2px;
            }
            QTreeWidget::item:selected { 
                background-color: #0078d4;
                color: white;
            }
            QTreeWidget::item:hover { 
                background-color: #4a4a4a;
                border-left: 3px solid #0078d4;
            }
        """)

    VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm', '.m4v'}

    @staticmethod
    def _count_videos(self, path=None, include_subdirs=None):
        """Compte le nombre total de vidéos (v1.0 compatible avec FolderTreeWidget et os.scandir)"""
        # Si aucun chemin n'est fourni, on récupère le dossier courant ou celui de l'arbre
        if path is None:
            path = getattr(self, 'current_folder', '')
            if not path and hasattr(self, 'folder_path'):
                path = self.folder_path
        
        # Si include_subdirs n'est pas spécifié, on regarde la configuration ou l'état de l'app
        if include_subdirs is None:
            include_subdirs = getattr(self, 'include_subdirs', False)
            if not include_subdirs and hasattr(self, 'config'):
                include_subdirs = self.config.get("last_include_subdirs", False)

        if not path or not os.path.exists(path):
            return 0

        count = 0
        video_extensions = ('.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v')
        image_extensions = tuple(self.image_extensions)
        media_extensions = video_extensions + image_extensions

        try:
            if include_subdirs:
                # Utilisation de os.walk (qui gère nativement scandir sous le capot)
                for root, _, files in os.walk(path):
                    for file in files:
                        if file.lower().endswith(media_extensions):
                            count += 1
            else:
                # Optimisation directe avec os.scandir pour la racine seule
                with os.scandir(path) as entries:
                    for entry in entries:
                        if entry.is_file() and entry.name.lower().endswith(media_extensions):
                            count += 1
        except Exception:
            pass
            
        return count

    @staticmethod
    def normalize_for_sort(text):
        replacements = {
            'à': 'a', 'á': 'a', 'â': 'a', 'ã': 'a', 'ä': 'a', 'å': 'a',
            'è': 'e', 'é': 'e', 'ê': 'e', 'ë': 'e',
            'ì': 'i', 'í': 'i', 'î': 'i', 'ï': 'i',
            'ò': 'o', 'ó': 'o', 'ô': 'o', 'õ': 'o', 'ö': 'o',
            'ù': 'u', 'ú': 'u', 'û': 'u', 'ü': 'u',
            'ý': 'y', 'ÿ': 'y',
            'ç': 'c',
            'À': 'A', 'Á': 'A', 'Â': 'A', 'Ã': 'A', 'Ä': 'A', 'Å': 'A',
            'È': 'E', 'É': 'E', 'Ê': 'E', 'Ë': 'E',
            'Ì': 'I', 'Í': 'I', 'Î': 'I', 'Ï': 'I',
            'Ò': 'O', 'Ó': 'O', 'Ô': 'O', 'Õ': 'O', 'Ö': 'O',
            'Ù': 'U', 'Ú': 'U', 'Û': 'U', 'Ü': 'U',
            'Ý': 'Y',
            'Ç': 'C'
        }
        result = []
        for char in text:
            result.append(replacements.get(char, char))
        return ''.join(result).lower()

    def _is_renameable(self, item):
        if item is None:
            return False
        root_files_only = item.data(0, Qt.ItemDataRole.UserRole.value + 2)
        return not root_files_only

    def viewportEvent(self, event):
        if event.type() == QEvent.Type.ToolTip:
            item = self.itemAt(event.pos())
            if item is not None:
                full_text = item.text(0)
                folder_name = full_text
                if folder_name.startswith("📂 ") or folder_name.startswith("📂 ") or folder_name.startswith("📄 "):
                    folder_name = folder_name[2:].strip()
                if "[" in folder_name:
                    folder_name = folder_name[:folder_name.rfind("[")].strip()
                
                rect = self.visualItemRect(item)
                font_metrics = QFontMetrics(self.font())
                text_width = font_metrics.horizontalAdvance(full_text)
                
                if text_width > rect.width():
                    QToolTip.showText(event.globalPos(), folder_name, self)
                else:
                    QToolTip.hideText()
                    
                return True
        
        return super().viewportEvent(event)

    def load_folder_tree(self, root_path, sort_ascending=True):
        self.sort_ascending = sort_ascending
        self.clear()

        root_item = QTreeWidgetItem(self)
        total = sum(
            self._count_videos(dp)
            for dp, _, _ in os.walk(root_path)
        )
        root_item.setText(0, f"📂 {os.path.basename(root_path)} (Tout)  [{total}]")
        root_item.setData(0, Qt.ItemDataRole.UserRole, root_path)
        root_item.setData(0, Qt.ItemDataRole.UserRole.value + 1, True)
        root_item.setData(0, Qt.ItemDataRole.UserRole.value + 2, False)

        root_count = self._count_videos(root_path)
        root_files_item = QTreeWidgetItem(root_item)
        root_files_item.setText(0, f"📄 Fichiers racine uniquement  [{root_count}]")
        root_files_item.setData(0, Qt.ItemDataRole.UserRole, root_path)
        root_files_item.setData(0, Qt.ItemDataRole.UserRole.value + 1, False)
        root_files_item.setData(0, Qt.ItemDataRole.UserRole.value + 2, True)

        self.add_subdirectories(root_item, root_path)
        self.expandAll()

    def add_subdirectories(self, parent_item, parent_path):
        try:
            dirs = sorted(
                [d for d in os.listdir(parent_path)
                 if os.path.isdir(os.path.join(parent_path, d))
                 and not d.startswith('.')
                 and d != "!JSON_Backups"],
                key=lambda x: self.normalize_for_sort(x),
                reverse=not self.sort_ascending
            )
            for item_name in dirs:
                item_path = os.path.join(parent_path, item_name)
                count = self._count_videos(item_path)
                folder_item = QTreeWidgetItem(parent_item)
                folder_item.setText(0, f"📁 {item_name}  [{count}]")
                folder_item.setData(0, Qt.ItemDataRole.UserRole, item_path)
                folder_item.setData(0, Qt.ItemDataRole.UserRole.value + 1, False)
                folder_item.setData(0, Qt.ItemDataRole.UserRole.value + 2, False)
                self.add_subdirectories(folder_item, item_path)
        except PermissionError:
            pass

    def on_item_clicked(self, item, column):
        folder_path = item.data(0, Qt.ItemDataRole.UserRole)
        include_subdirs = item.data(0, Qt.ItemDataRole.UserRole.value + 1)
        root_files_only = item.data(0, Qt.ItemDataRole.UserRole.value + 2)
        if folder_path:
            self.parent_viewer.load_videos_from_path(folder_path, include_subdirs, root_files_only)

    def on_item_double_clicked(self, item, column):
        if self._is_renameable(item):
            self.start_rename(item)

    def show_context_menu(self, pos):
        from PyQt6.QtWidgets import QMenu
        item = self.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2a2d3a;
                color: #e8eaf0;
                border: 1px solid #4a5270;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px 6px 12px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #0078d4;
            }
            QMenu::separator {
                height: 1px;
                background: #4a5270;
                margin: 3px 6px;
            }
        """)
        if self._is_renameable(item):
            act_rename = menu.addAction("✏️  Renommer")
            act_rename.triggered.connect(lambda: self.start_rename(item))
            menu.addSeparator()
            act_delete = menu.addAction("🗑️  Supprimer")
            act_delete.triggered.connect(lambda: self.delete_folder(item))
        menu.exec(self.viewport().mapToGlobal(pos))

    def delete_folder(self, item):
        folder_path = item.data(0, Qt.ItemDataRole.UserRole)
        if not folder_path or not os.path.isdir(folder_path):
            self.parent_viewer.status_bar.set_error("Dossier introuvable")
            return

        folder_name = os.path.basename(folder_path)

        try:
            contents = list(os.scandir(folder_path))
        except Exception as e:
            self.parent_viewer.status_bar.set_error(f"Impossible de lire le dossier : {e}")
            return

        if contents:
            msg = (
                f"Le dossier « {folder_name} » contient {len(contents)} élément(s).\n\n"
                f"Voulez-vous le supprimer définitivement avec tout son contenu ?"
            )
        else:
            msg = f"Voulez-vous supprimer définitivement le dossier vide « {folder_name} » ?"

        reply = QMessageBox.question(
            self, "Confirmer la suppression", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            self.parent_viewer.status_bar.set_info("Suppression annulée")
            return

        try:
            shutil.rmtree(folder_path)
            parent = item.parent()
            if parent:
                parent.removeChild(item)
            else:
                idx = self.indexOfTopLevelItem(item)
                if idx >= 0:
                    self.takeTopLevelItem(idx)
            self.parent_viewer.status_bar.set_success(f"Dossier « {folder_name} » supprimé")
            if self.parent_viewer.current_folder and (
                self.parent_viewer.current_folder == folder_path
                or self.parent_viewer.current_folder.startswith(folder_path + os.sep)
            ):
                self.parent_viewer.current_folder = None
                self.parent_viewer.video_files = []
                self.parent_viewer.display_videos()
        except Exception as e:
            self.parent_viewer.status_bar.set_error(f"Erreur de suppression : {e}")

    def start_rename(self, item):
        folder_path = item.data(0, Qt.ItemDataRole.UserRole)
        old_name = os.path.basename(folder_path)

        rect = self.visualItemRect(item)
        self._rename_edit = QLineEdit(self.viewport())
        self._rename_edit.setText(old_name)
        self._rename_edit.setGeometry(rect)
        self._rename_edit.setStyleSheet(
            "background-color: #1e1e1e; color: white; border: 2px solid #0078d4; padding: 2px;"
        )
        self._rename_edit.selectAll()
        self._rename_edit.show()
        self._rename_edit.setFocus()
        self._rename_item = item
        self._rename_old_path = folder_path

        self._rename_edit.returnPressed.connect(self.commit_rename)
        self._rename_edit.editingFinished.connect(self.cancel_rename_if_needed)

    def commit_rename(self):
        if not hasattr(self, '_rename_edit') or self._rename_edit is None:
            return
        new_name = self._rename_edit.text().strip()
        old_path = self._rename_old_path
        parent_path = os.path.dirname(old_path)
        new_path = os.path.join(parent_path, new_name)

        self._rename_edit.hide()
        self._rename_edit.deleteLater()
        self._rename_edit = None

        if not new_name or new_name == os.path.basename(old_path):
            return

        # --- Libérer les ressources avant renommage ---
        # Arrêter la lecture vidéo
        self.parent_viewer.vlc_player.stop()

        # Si le dossier à renommer est le dossier courant ou un parent, on décharge l'affichage
        if self.parent_viewer.current_folder and (
            self.parent_viewer.current_folder == old_path or
            self.parent_viewer.current_folder.startswith(old_path + os.sep)
        ):
            self.parent_viewer.current_folder = None
            self.parent_viewer.video_files = []
            self.parent_viewer.all_video_files = []
            self.parent_viewer.display_videos()
            self.parent_viewer.status_bar.set_info("Dossier en cours de renommage...")
        QApplication.processEvents()
        # ---------------------------------------------

        try:
            os.rename(old_path, new_path)
            count = FolderTreeWidget._count_videos(new_path)
            self._rename_item.setText(0, f"📁 {new_name}  [{count}]")
            self._rename_item.setData(0, Qt.ItemDataRole.UserRole, new_path)
            self.parent_viewer.status_bar.set_success(f"Dossier renommé : {new_name}")
            # Si le dossier renommé était le dossier courant, on recharge le nouveau chemin
            if self.parent_viewer.current_folder is None and old_path == self.parent_viewer.current_folder:
                # normalement current_folder est déjà None
                pass
            # On recharge l'arbre pour mettre à jour les éventuels sous-dossiers
            self.parent_viewer.refresh_folder_tree()
        except Exception as e:
            self.parent_viewer.status_bar.set_error(f"Erreur de renommage : {e}")

    def cancel_rename_if_needed(self):
        if hasattr(self, '_rename_edit') and self._rename_edit is not None:
            self._rename_edit.hide()
            self._rename_edit.deleteLater()
            self._rename_edit = None

    def dragEnterEvent(self, event):
        if not self.parent_viewer.management_mode:
            return
        if event.mimeData().hasText():
            video_path = event.mimeData().text()
            if any(video_path.lower().endswith(ext) for ext in self.VIDEO_EXTENSIONS):
                event.acceptProposedAction()
    
    def dragMoveEvent(self, event):
        if not self.parent_viewer.management_mode:
            return
        if event.mimeData().hasText():
            event.acceptProposedAction()
            item = self.itemAt(event.position().toPoint())
            if item != getattr(self, '_drag_hover_item', None):
                old = getattr(self, '_drag_hover_item', None)
                if old is not None:
                    old.setBackground(0, old.data(0, Qt.ItemDataRole.UserRole.value + 10) or __import__('PyQt6.QtGui', fromlist=['QBrush']).QBrush())
                self._drag_hover_item = item
                if item is not None:
                    from PyQt6.QtGui import QBrush, QColor
                    item.setData(0, Qt.ItemDataRole.UserRole.value + 10, item.background(0))
                    item.setBackground(0, QBrush(QColor("#1a6a3a")))

    def dragLeaveEvent(self, event):
        old = getattr(self, '_drag_hover_item', None)
        if old is not None:
            from PyQt6.QtGui import QBrush
            old.setBackground(0, old.data(0, Qt.ItemDataRole.UserRole.value + 10) or QBrush())
        self._drag_hover_item = None
        super().dragLeaveEvent(event)
    
    def dropEvent(self, event):
        old = getattr(self, '_drag_hover_item', None)
        if old is not None:
            from PyQt6.QtGui import QBrush
            old.setBackground(0, old.data(0, Qt.ItemDataRole.UserRole.value + 10) or QBrush())
        self._drag_hover_item = None

        if not self.parent_viewer.management_mode:
            return
            
        item = self.itemAt(event.position().toPoint())
        if item is None:
            return
        
        target_folder = item.data(0, Qt.ItemDataRole.UserRole)
        if not target_folder or not os.path.isdir(target_folder):
            self.parent_viewer.status_bar.set_error("Dossier cible invalide")
            return
        
        video_path = event.mimeData().text()
        if not os.path.exists(video_path):
            self.parent_viewer.status_bar.set_error("Fichier source introuvable")
            return
        
        filename = os.path.basename(video_path)
        dest_path = os.path.join(target_folder, filename)
        
        if os.path.exists(dest_path):
            reply = QMessageBox.question(
                self, "Fichier existant",
                f"Le fichier '{filename}' existe déjà dans ce dossier.\n\nVoulez-vous le remplacer ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                self.parent_viewer.status_bar.set_info("Déplacement annulé")
                return
            try:
                os.remove(dest_path)
            except Exception as e:
                self.parent_viewer.status_bar.set_error(f"Impossible de supprimer le fichier existant : {e}")
                return
        
        try:
            # Arrêter la prévisualisation pour libérer le fichier
            self.parent_viewer.vlc_player.stop()
            QApplication.processEvents()
            
            # Effectuer le déplacement physique
            shutil.move(video_path, dest_path)
            
            # --- v7.4 : Mise à jour des métadonnées dans le store central ---
            ds = self.parent_viewer._get_data_store()
            if ds:
                ds.update_path(video_path, dest_path)
            # -----------------------------------------------------------------
            
            self.parent_viewer.status_bar.set_success(f"'{filename}' déplacé vers {os.path.basename(target_folder)}")
            self.parent_viewer.refresh_after_move()
            event.acceptProposedAction()
        except Exception as e:
            self.parent_viewer.status_bar.set_error(f"Erreur de déplacement : {e}")


class FilmTreeWidget(QListWidget):
    """Liste des films virtuels (mode Par films)"""

    VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm', '.m4v'}

    def __init__(self, parent_viewer):
        super().__init__()
        self.parent_viewer = parent_viewer
        self._film_map = {}

        self.setStyleSheet("""
            QListWidget {
                background-color: #2b2b2b;
                color: white;
                border: 1px solid #555;
            }
            QListWidget::item { padding: 4px 6px; border-bottom: 1px solid #3a3a3a; }
            QListWidget::item:selected { background-color: #0078d4; }
            QListWidget::item:hover { background-color: #3b3b3b; }
        """)
        self.itemClicked.connect(self.on_film_clicked)

    @staticmethod
    def extract_film_name(filename):
        name = os.path.splitext(filename)[0]
        if " - " in name:
            return name.split(" - ", 1)[0].strip()
        return name.strip()

    def load_films(self, root_path, sort_ascending=True):
        self.clear()
        self._film_map = {}

        for dirpath, dirs, files in os.walk(root_path):
            dirs[:] = [d for d in dirs if d != ".normalized_backup"]
            for f in files:
                if os.path.splitext(f)[1].lower() in self.VIDEO_EXTENSIONS:
                    film = self.extract_film_name(f)
                    self._film_map.setdefault(film, []).append(os.path.join(dirpath, f))

        films_sorted = sorted(
            self._film_map.keys(),
            key=lambda x: FolderTreeWidget.normalize_for_sort(x),
            reverse=not sort_ascending
        )
        for film in films_sorted:
            count = len(self._film_map[film])
            item = QListWidgetItem(f"🎬  {film}  ({count})")
            item.setData(Qt.ItemDataRole.UserRole, film)
            self.addItem(item)

    def on_film_clicked(self, item):
        film = item.data(Qt.ItemDataRole.UserRole)
        if film and film in self._film_map:
            paths = sorted(self._film_map[film])
            self.parent_viewer.load_video_list(paths, label=film)

class FolderDataStore:
    """
    Gestionnaire du fichier unique _videoviewer_data.json à la racine du dossier source.
    Stocke pour chaque vidéo (chemin relatif) :
        - tags
        - backups
        - audio_cache
        - norm_history
        - copy_count
    """
    FILENAME = "_videoviewer_data.json"

    def __init__(self, root_folder_path):
        self.root_path = os.path.abspath(root_folder_path)
        self._data = {}   # {rel_path: { ... }}
        self._load()

    def _json_path(self):
        return os.path.join(self.root_path, self.FILENAME)

    def _load(self):
        try:
            p = self._json_path()
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
        except Exception:
            self._data = {}

    def save(self):
        try:
            with open(self._json_path(), 'w', encoding='utf-8') as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _make_rel_path(self, abs_path):
        """Convertit un chemin absolu en chemin relatif par rapport à la racine.
        Si le fichier n'est pas sous la racine, retourne le nom de base seul
        (ce qui peut arriver temporairement après un changement de dossier)."""
        try:
            # Normaliser les chemins pour éviter les problèmes de casse ou de slash
            abs_path = os.path.normpath(os.path.abspath(abs_path))
            root = os.path.normpath(self.root_path)
            # Vérifier si abs_path commence par root
            if os.path.commonpath([abs_path, root]) != root:
                # Le fichier n'est pas sous la racine, on utilise juste le nom
                return os.path.basename(abs_path)
            rel = os.path.relpath(abs_path, root)
            return rel.replace('\\', '/')
        except (ValueError, OSError):
            # En cas d'erreur, retourner le nom de fichier
            return os.path.basename(abs_path)

    def _entry(self, abs_path):
        """Retourne le dictionnaire correspondant à un fichier (créé si nécessaire)."""
        rel = self._make_rel_path(abs_path)
        if rel not in self._data:
            self._data[rel] = {}
        return self._data[rel]

    # ---------- Tags ----------
    def get_tags(self, abs_path):
        return list(self._entry(abs_path).get("tags", []))

    def set_tags(self, abs_path, tags):
        self._entry(abs_path)["tags"] = sorted(set(tags))
        self.save()

    def add_tag(self, abs_path, tag):
        tag = tag.strip().lower()
        if not tag:
            return
        entry = self._entry(abs_path)
        tags = set(entry.get("tags", []))
        tags.add(tag)
        entry["tags"] = sorted(tags)
        
        # --- Nettoyage : retirer le tag de _global_tags s'il y était ---
        global_entry = self._data.get("_global_tags")
        if global_entry and "tags" in global_entry:
            global_tags = global_entry["tags"]
            if tag in global_tags:
                global_tags.remove(tag)
                if not global_tags:  # optionnel : supprimer la clé si vide
                    del global_entry["tags"]
                self.save()  # sauvegarde après modification des deux parties
            else:
                self.save()
        else:
            self.save()

    def remove_tag(self, abs_path, tag):
        entry = self._entry(abs_path)
        tags = set(entry.get("tags", []))
        tags.discard(tag)
        entry["tags"] = sorted(tags)
        
        # Vérifier si le tag est encore utilisé ailleurs
        still_used = False
        for rel, data in self._data.items():
            if rel == "_global_tags":
                continue
            if tag in data.get("tags", []):
                still_used = True
                break
        
        # S'il n'est plus utilisé, l'ajouter à _global_tags
        if not still_used:
            global_entry = self._data.setdefault("_global_tags", {})
            global_tags = global_entry.setdefault("tags", [])
            if tag not in global_tags:
                global_tags.append(tag)
                global_entry["tags"] = sorted(global_tags)
        
        self.save()

    def all_tags(self):
        """Retourne {tag: count} pour tous les fichiers du dossier source."""
        counts = {}
        # Tags orphelins (sans fichier)
        global_entry = self._data.get("_global_tags", {})
        for t in global_entry.get("tags", []):
            if t not in counts:
                counts[t] = 0
        for rel, entry in self._data.items():
            if rel == "_global_tags":
                continue
            for t in entry.get("tags", []):
                counts[t] = counts.get(t, 0) + 1
        return counts

    def files_with_tag(self, tag):
        """Retourne la liste des chemins relatifs ayant ce tag."""
        return [rel for rel, entry in self._data.items()
                if tag in entry.get("tags", [])]
    
    def get_tag_valence(self, tag):
        """Retourne la valence du tag, ou None si non définie."""
        self._ensure_tag_valences()
        # Normaliser en minuscules comme lors de l'ajout
        normalized = tag.strip().lower()
        return self._data["_tag_valences"].get(normalized)

    # ---------- Sauvegardes ----------
    def get_backups(self, abs_path):
        return list(self._entry(abs_path).get("backups", []))

    def add_backup(self, abs_path, dest_label):
        from datetime import date
        entry = self._entry(abs_path)
        backups = entry.get("backups", [])
        backups.append({"dest": dest_label, "date": date.today().strftime("%d/%m/%Y")})
        entry["backups"] = backups
        self.save()

    def is_backed_up(self, abs_path, dest_label=None):
        backups = self.get_backups(abs_path)
        if not backups:
            return False
        if dest_label is None:
            return True
        return any(b["dest"] == dest_label for b in backups)

    def backup_status(self, abs_path, dest_labels):
        if not dest_labels:
            backups = self.get_backups(abs_path)
            return "all" if backups else "none"
        backed = [d for d in dest_labels if self.is_backed_up(abs_path, d)]
        if len(backed) == len(dest_labels):
            return "all"
        if backed:
            return "partial"
        return "none"

    # ---------- Cache audio ----------
    def get_audio_cache(self, abs_path):
        return self._entry(abs_path).get("audio_cache")

    def set_audio_cache(self, abs_path, data):
        self._entry(abs_path)["audio_cache"] = data
        self.save()

    # ---------- Historique de normalisation ----------
    def get_norm_history(self, abs_path):
        return self._entry(abs_path).get("norm_history")

    def set_norm_history(self, abs_path, info):
        self._entry(abs_path)["norm_history"] = info
        self.save()

    def clear_norm_history(self, abs_path):
        entry = self._entry(abs_path)
        if "norm_history" in entry:
            del entry["norm_history"]
            self.save()

    # ---------- Compteur de copies ----------
    def get_copy_count(self, abs_path):
        return self._entry(abs_path).get("copy_count", 0)

    def increment_copy_count(self, abs_path):
        entry = self._entry(abs_path)
        count = entry.get("copy_count", 0) + 1
        entry["copy_count"] = count
        print(f"[DEBUG STORE] increment_copy_count pour {self._make_rel_path(abs_path)} : {count-1} -> {count}")
        self.save()
        return count
    
    def decrement_copy_count(self, abs_path):
        entry = self._entry(abs_path)
        count = max(0, entry.get("copy_count", 0) - 1)
        entry["copy_count"] = count
        self.save()
        return count

    # ---------- Gestion des déplacements ----------
    def update_path(self, old_abs_path, new_abs_path):
        """Appelé après un déplacement de fichier pour mettre à jour la clé."""
        old_rel = self._make_rel_path(old_abs_path)
        new_rel = self._make_rel_path(new_abs_path)
        if old_rel in self._data:
            self._data[new_rel] = self._data.pop(old_rel)
            self.save()

    # ---------- Migration depuis l'ancien format global ----------
    def import_from_global_config(self, audio_cache, norm_history, copy_counts):
        """Importe les données de l'ancien JSON de config global."""
        changed = False
        for abs_path, val in audio_cache.items():
            try:
                rel = self._make_rel_path(abs_path)
                entry = self._data.setdefault(rel, {})
                if "audio_cache" not in entry:
                    entry["audio_cache"] = val
                    changed = True
            except ValueError:
                pass
        for abs_path, val in norm_history.items():
            try:
                rel = self._make_rel_path(abs_path)
                entry = self._data.setdefault(rel, {})
                if "norm_history" not in entry:
                    entry["norm_history"] = val
                    changed = True
            except ValueError:
                pass
        for abs_path, val in copy_counts.items():
            try:
                rel = self._make_rel_path(abs_path)
                entry = self._data.setdefault(rel, {})
                if "copy_count" not in entry:
                    entry["copy_count"] = val
                    changed = True
            except ValueError:
                pass
        if changed:
            self.save()

    # ---------- Métadonnées des tags (valence) ----------
    def _ensure_tag_valences(self):
        """Crée la section _tag_valences si elle n'existe pas."""
        if "_tag_valences" not in self._data:
            self._data["_tag_valences"] = {}

    def set_tag_valence(self, tag, valence):
        """
        Définit la valence d'un tag.
        valence : 'positif', 'negatif', 'neutre'
        """
        if valence not in ("positif", "negatif", "neutre"):
            return
        self._ensure_tag_valences()
        self._data["_tag_valences"][tag] = valence
        self.save()

    def set_tag_valence(self, tag, valence):
        """
        Définit la valence d'un tag.
        valence : 'positif', 'negatif', 'neutre' ou None pour supprimer.
        """
        if valence not in ("positif", "negatif", "neutre", None):
            return
        self._ensure_tag_valences()
        if valence is None:
            # Supprimer la valence si elle existe
            if tag in self._data["_tag_valences"]:
                del self._data["_tag_valences"][tag]
        else:
            self._data["_tag_valences"][tag] = valence
        self.save()

    def remove_tag_valence(self, tag):
        """Supprime la valence associée à un tag, sans erreur s'il n'existe pas."""
        self._ensure_tag_valences()
        self._data["_tag_valences"].pop(tag, None)
        self.save()



class TagListWidget(QListWidget):
    """Sous-classe propre pour gérer les événements PyQt6 sans monkey-patching"""
    def __init__(self, panel):
        super().__init__()
        self.panel = panel

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        item = self.itemAt(event.pos())
        if item is None:
            super().mousePressEvent(event)
            return
        # On passe la main à la logique du panel
        self.panel._handle_tag_click(item)

    def dragEnterEvent(self, event):
        if (self.panel.parent_viewer.management_mode
                and (event.mimeData().hasFormat("application/x-videopath")
                     or event.mimeData().hasFormat("application/x-videopath-list"))):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if (self.panel.parent_viewer.management_mode
                and (event.mimeData().hasFormat("application/x-videopath")
                     or event.mimeData().hasFormat("application/x-videopath-list"))):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.panel._list_drag_leave(event)

    def dropEvent(self, event):
        self.panel._list_drop(event)


class TagPanelWidget(QWidget):
    """
    Panneau de navigation par tags.
    Remplace FolderTreeWidget quand un dossier à plat est sélectionné.
    Coexiste avec FolderTreeWidget pour la compatibilité avec les structures
    à sous-dossiers existantes.
    v7.2 : clic droit sur un tag (supprimer/renommer) + comptage au survol des filtres système.
    """
    tag_filter_changed = pyqtSignal(list)   # émet la liste des tags actifs

    SYSTEM_FILTERS = [
        ("all",        "  Tous",                "#555"),
        ("none",       "  Non sauvegardés",     "#8b2020"),
        ("backed",     "  Sauvegardés",          "#1a5a1a"),
        ("untagged",   "  Sans tag",             "#555"),
        ("multitag",   "  Multi‑tags",           "#555"),
    ]

    def __init__(self, parent_viewer):
        super().__init__()
        self.parent_viewer = parent_viewer
        self._active_system = "all"
        self._active_tags = []
        self._selected_tags_set = set()
        self._filter_counts = {"all": 0, "none": 0, "backed": 0, "untagged": 0}
        self._valence_filter = None   # Aucun filtre de valence par défaut
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # -- Filtres système -----------------------------------------------
        sys_label = QLabel("-- Filtres --")
        sys_label.setStyleSheet("color: #666; font-size: 10px; padding: 4px 6px 2px 6px;")
        layout.addWidget(sys_label)

        self._sys_btns = {}

        # --- Ligne pour "Tous" seulement ---
        row_backup = QHBoxLayout()
        row_backup.setSpacing(4)
        # Bouton décoratif avec icône "film" (non cliquable)
        btn_film_icon = QPushButton()
        btn_film_icon.setEnabled(False)  # désactivé = aspect grisé, non cliquable
        btn_film_icon.setStyleSheet("""
            QPushButton {
                background-color: #777777;
                border: none;
                border-radius: 4px;
                padding: 4px;
            }
            QPushButton:disabled {
                background-color: #777777;
                color: white;
            }
        """)
        icon_film = self.parent_viewer.fa_svg_icon("film", size=16, color="#ffffff")
        if icon_film and not icon_film.isNull():
            btn_film_icon.setIcon(icon_film)
            btn_film_icon.setIconSize(QSize(16, 16))

        btn_film_icon.setFixedSize(32, 28)  # taille carrée arrondie
        # Tooltip instantané "Vidéos" sur le bouton décoratif
        def _film_icon_enter(event):
            InstantTooltip.get(self.parent_viewer).show_at("Vidéos", event.globalPosition().toPoint())

        def _film_icon_leave(event):
            InstantTooltip.get(self.parent_viewer).hide_tip()

        btn_film_icon.enterEvent = _film_icon_enter
        btn_film_icon.leaveEvent = _film_icon_leave
        btn_film_icon.setToolTip("")   # désactive le tooltip natif        
        row_backup.addWidget(btn_film_icon, 1)

        # Bouton "Tous" (all)
        btn_all = QPushButton("Tous")
        btn_all.setCheckable(True)
        btn_all.setChecked(True)   # activé par défaut
        btn_all.setStyleSheet(self._filter_button_style("#444", "#5a5a5a", "#3a3a3a"))
        btn_all.clicked.connect(lambda checked: self._on_system_filter("all"))
        btn_all.setToolTip("")
        self._sys_btns["all"] = btn_all
        row_backup.addWidget(btn_all, 1)

        layout.addLayout(row_backup)

        # --- Ligne "Tags :" + filtres Sans / Multi (1/3 chacun) ---
        row_tags = QHBoxLayout()
        row_tags.setSpacing(4)

        # Bouton décoratif avec icône "tags" (non cliquable)
        btn_tags_icon = QPushButton()
        btn_tags_icon.setEnabled(False)  # désactivé -> non cliquable, aspect grisé
        btn_tags_icon.setStyleSheet("""
            QPushButton {
                background-color: #777777;
                border: none;
                border-radius: 4px;
                padding: 4px;
            }
            QPushButton:disabled {
                background-color: #777777;
                color: white;
            }
        """)
        icon_tags = self.parent_viewer.fa_svg_icon("tags", size=16, color="#ffffff")
        if icon_tags and not icon_tags.isNull():
            btn_tags_icon.setIcon(icon_tags)
            btn_tags_icon.setIconSize(QSize(16, 16))
        btn_tags_icon.setFixedSize(32, 28)  # taille carrée arrondie

        # Tooltip instantané "Tags" sur le bouton décoratif
        def _tags_icon_enter(event):
            InstantTooltip.get(self.parent_viewer).show_at("Tags", event.globalPosition().toPoint())

        def _tags_icon_leave(event):
            InstantTooltip.get(self.parent_viewer).hide_tip()

        btn_tags_icon.enterEvent = _tags_icon_enter
        btn_tags_icon.leaveEvent = _tags_icon_leave
        btn_tags_icon.setToolTip("")   # désactive le tooltip natif
        row_tags.addWidget(btn_tags_icon, 1)

        btn_untagged = QPushButton("Sans")
        btn_untagged.setCheckable(True)
        btn_untagged.setChecked(False)
        btn_untagged.setStyleSheet(self._filter_button_style("#444", "#5a5a5a", "#3a3a3a"))
        btn_untagged.clicked.connect(lambda checked: self._on_system_filter("untagged"))
        btn_untagged.setToolTip("")
        self._sys_btns["untagged"] = btn_untagged
        row_tags.addWidget(btn_untagged, 1)

        btn_multitag = QPushButton("Multi")
        btn_multitag.setCheckable(True)
        btn_multitag.setChecked(False)
        btn_multitag.setStyleSheet(self._filter_button_style("#444", "#5a5a5a", "#3a3a3a"))
        btn_multitag.clicked.connect(lambda checked: self._on_system_filter("multitag"))
        btn_multitag.setToolTip("")
        self._sys_btns["multitag"] = btn_multitag
        row_tags.addWidget(btn_multitag, 1)

        layout.addLayout(row_tags)

        # Réactiver les tooltips instantanés (sera fait après)
        QTimer.singleShot(0, self._install_instant_tooltips)

        # --- Ligne "Valence :" + boutons Tous / Positif / Négatif / Neutre ---
        row_valence = QHBoxLayout()
        row_valence.setSpacing(4)

        # Bouton décoratif avec icône "temperature-high" (non cliquable)
        btn_valence_icon = QPushButton()
        btn_valence_icon.setEnabled(False)  # désactivé -> aspect grisé, non cliquable
        btn_valence_icon.setStyleSheet("""
            QPushButton {
                background-color: #777777;
                border: none;
                border-radius: 4px;
                padding: 4px;
            }
            QPushButton:disabled {
                background-color: #777777;
                color: white;
            }
        """)
        icon_valence = self.parent_viewer.fa_svg_icon("temperature-high", size=16, color="#ffffff")
        if icon_valence and not icon_valence.isNull():
            btn_valence_icon.setIcon(icon_valence)
            btn_valence_icon.setIconSize(QSize(16, 16))
        btn_valence_icon.setFixedSize(32, 28)  # taille carrée arrondie
        # Tooltip instantané "Valence" sur le bouton décoratif
        def _valence_icon_enter(event):
            InstantTooltip.get(self.parent_viewer).show_at("Valence", event.globalPosition().toPoint())

        def _valence_icon_leave(event):
            InstantTooltip.get(self.parent_viewer).hide_tip()

        btn_valence_icon.enterEvent = _valence_icon_enter
        btn_valence_icon.leaveEvent = _valence_icon_leave
        btn_valence_icon.setToolTip("")   # désactive le tooltip natif
        row_valence.addWidget(btn_valence_icon, 1)

        # Initialisation de la valence : aucun filtre par défaut
        self._valence_filter = None

        # Création des 4 boutons de valence
        self._valence_btns = {}
        valence_states = [
            ("all",     "Tous"),
            ("positif", "Positif"),
            ("negatif", "Négatif"),
            ("neutre",  "Neutre"),
        ]
        for val_key, val_label in valence_states:
            btn = QPushButton(val_label)
            btn.setCheckable(True)
            btn.setChecked(False)   # aucun coché par défaut
            btn.setStyleSheet(self._filter_button_style("#444", "#5a5a5a", "#3a3a3a"))
            btn.clicked.connect(lambda checked, v=val_key: self._set_valence_filter(v))
            btn.setToolTip("")
            self._valence_btns[val_key] = btn
            row_valence.addWidget(btn, 1)

        layout.addLayout(row_valence)

        # -- Séparateur ----------------------------------------------------
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("QFrame { color: #444; margin: 4px 0; }")
        layout.addWidget(sep)

        # -- En-tête Tags + bouton -----------------------------------------
        tag_header = QHBoxLayout()
        tag_label = QLabel("-- Mes tags --")
        tag_label.setStyleSheet("color: #666; font-size: 10px; padding: 2px 6px;")
        tag_header.addWidget(tag_label)
        tag_header.addStretch()

        btn_clear = QPushButton("?")
        btn_clear.setFixedSize(18, 18)
        btn_clear.setToolTip("Effacer la sélection de tags")
        btn_clear.setStyleSheet("""
            QPushButton { background: transparent; color: #888; border: none; font-size: 10px; }
            QPushButton:hover { color: white; }
        """)
        btn_clear.clicked.connect(self._clear_tag_selection)
        tag_header.addWidget(btn_clear)
        layout.addLayout(tag_header)

        # -- Liste de tags scrollable ---------------------------------------
        self._tag_list = TagListWidget(self)
        self._tag_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._tag_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._selected_tags_set = set()   # état de sélection géré manuellement
        self._tag_list.setStyleSheet("""
            QListWidget {
                background-color: #1e1e1e;
                color: white;
                border: none;
                outline: none;
            }
            QListWidget::item { padding: 4px 8px; border-bottom: 1px solid #2a2a2a; }
            QListWidget::item:hover { background-color: #303050; color: white; }
            QListWidget::item:selected { background-color: #1a4a7a; color: white; }
            QListWidget::item:selected:hover { background-color: #2060a0; color: white; }
        """)

        # menu contextuel clic droit
        self._tag_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tag_list.customContextMenuRequested.connect(self._show_tag_context_menu)
        self._tag_list.setAcceptDrops(True)
        self._tag_list.viewport().setAcceptDrops(True)
        self._drag_hover_item = None
        layout.addWidget(self._tag_list, stretch=1)

        # -- Bouton nouveau tag ---------------------------------------------
        btn_new = QPushButton("+ Nouveau tag")
        btn_new.setStyleSheet("""
            QPushButton {
                background-color: #444;
                color: #aaa;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 5px;
                font-size: 11px;
                font-weight: normal;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
                color: white;
                border: 1px solid #5a5a5a;
            }
            QPushButton:pressed {
                background-color: #3a3a3a;
                border: 1px solid #3a3a3a;
            }
        """)
        btn_new.clicked.connect(self._create_new_tag)
        layout.addWidget(btn_new)


    def _filter_button_style(self, normal_bg, hover_bg, checked_bg):
        """Retourne la feuille de style pour un bouton filtre avec les gris donnés."""
        return f"""
            QPushButton {{
                background-color: {normal_bg};
                color: white;
                border: none;
                padding: 5px 8px;
                text-align: center;
                font-size: 11px;
                border-radius: 3px;
            }}
            QPushButton:hover {{
                background-color: {hover_bg};
            }}
            QPushButton:checked {{
                background-color: {checked_bg};
                border-left: 3px solid #0078d4;
                font-weight: bold;
            }}
        """

    # Comptage précalculé pour les tooltips des filtres ----------
    def _compute_filter_counts(self, data_store, all_video_files, backup_dests):
        """Calcule le nombre de vidéos par filtre système. Appelé une fois dans refresh()."""
        
        counts = {"all": 0, "none": 0, "backed": 0, "untagged": 0, "multitag": 0}
        if not all_video_files:
            return counts
        
        dest_labels = [d["label"] for d in (backup_dests or [])]
        counts["all"] = len(all_video_files)
        # Initialiser les compteurs de valence
        counts["valence_all"] = 0
        counts["valence_positif"] = 0
        counts["valence_negatif"] = 0
        counts["valence_neutre"] = 0

        for path in all_video_files:
            tags = data_store.get_tags(path) if data_store else []
            if not tags:
                counts["untagged"] += 1
            if len(tags) >= 2:
                counts["multitag"] += 1

            # Valences : on compte le fichier s'il possède au moins un tag avec la valence donnée
            has_pos = False
            has_neg = False
            has_neu = False
            if data_store:
                for t in tags:
                    v = data_store.get_tag_valence(t)
                    if v == "positif":
                        has_pos = True
                    elif v == "negatif":
                        has_neg = True
                    elif v == "neutre":
                        has_neu = True
            if has_pos or has_neg or has_neu:
                counts["valence_all"] += 1
            if has_pos:
                counts["valence_positif"] += 1
            if has_neg:
                counts["valence_negatif"] += 1
            if has_neu:
                counts["valence_neutre"] += 1

            # Sauvegarde : non implémenté, tous = non sauvegardés
            counts["none"] += 1

        return counts

    def _update_filter_tooltips(self):
        """Met à jour les données de tooltip des boutons filtres (affichage via InstantTooltip)."""
        labels = {
            "all":      "Tous",
            "none":     "Non sauvegardés",
            "backed":   "Sauvegardés",
            "untagged": "Sans tag",
            "multitag": "Multi‑tags",
        }
        for key, btn in self._sys_btns.items():
            n = self._filter_counts.get(key, 0)
            plural = "vidéo" if n <= 1 else "vidéos"
            btn.setProperty("tip_text", f"{n} {plural}")

    def _install_instant_tooltips(self):
        """Installe enterEvent/leaveEvent sur les boutons filtres pour InstantTooltip."""
        # Boutons système
        for key, btn in self._sys_btns.items():
            def _enter(event, b=btn):
                tip = b.property("tip_text")
                if tip:
                    InstantTooltip.get(self.parent_viewer).show_at(
                        tip, event.globalPosition().toPoint()
                    )
            def _leave(event):
                InstantTooltip.get(self.parent_viewer).hide_tip()
            btn.enterEvent = _enter
            btn.leaveEvent = _leave
            btn.setToolTip("")

        # Boutons de valence (ajoutés ici)
        for key, btn in self._valence_btns.items():
            def _enter_val(event, b=btn):
                tip = b.property("tip_text")
                if tip:
                    InstantTooltip.get(self.parent_viewer).show_at(
                        tip, event.globalPosition().toPoint()
                    )
            def _leave_val(event):
                InstantTooltip.get(self.parent_viewer).hide_tip()
            btn.enterEvent = _enter_val
            btn.leaveEvent = _leave_val
            btn.setToolTip("")

    def refresh(self, data_store, backup_dests=None):
        """Met à jour la liste des tags depuis le FolderDataStore."""

        # --- SAUVEGARDE DE LA POSITION DE DÉFILEMENT ---
        scrollbar = self._tag_list.verticalScrollBar()
        scroll_value = scrollbar.value()
        # ---------------------------------------------

        prev_selected = set(self._active_tags)
        self._tag_list.clear()
        tag_counts = data_store.all_tags() if data_store else {}
        
        # --- NOUVEAU : Filtrer les tags par valence si nécessaire ---
        valence_filter = getattr(self, '_valence_filter', "all")
        if valence_filter is not None and valence_filter != "all":
            filtered_counts = {}
            for tag, count in tag_counts.items():
                if data_store.get_tag_valence(tag) == valence_filter:
                    filtered_counts[tag] = count
            tag_counts = filtered_counts
        # ------------------------------------------------------------

        ascending = True
        if hasattr(self.parent_viewer, 'sort_ascending'):
            ascending = self.parent_viewer.sort_ascending
        else:
            ascending = True

        for tag in sorted(tag_counts.keys(), reverse=not ascending):
            count = tag_counts[tag]
            valence = data_store.get_tag_valence(tag) if data_store else None

            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, tag)
            if tag in prev_selected:
                item.setSelected(True)

            widget = QWidget()
            outer_layout = QHBoxLayout(widget)
            outer_layout.setContentsMargins(0, 0, 4, 0)
            outer_layout.setSpacing(0)

            # Barre verticale de sélection (masquée par défaut)
            bar = QFrame()
            bar.setFixedWidth(3)
            bar.setStyleSheet("background-color: #0078d4; border-radius: 1px;")
            bar.setVisible(tag in self._selected_tags_set)
            widget.setProperty("selection_bar", bar)
            outer_layout.addWidget(bar)

            inner = QWidget()
            layout = QHBoxLayout(inner)
            layout.setContentsMargins(6, 2, 0, 2)
            layout.setSpacing(6)
            outer_layout.addWidget(inner, 1)

            lbl_text = QLabel(f"{tag}  ({count})")
            lbl_text.setStyleSheet("color: white; font-size: 12px;")
            layout.addWidget(lbl_text)
            layout.addStretch()

            if valence is not None:
                # Déterminer l'icône et la couleur selon la valence
                icone_map = {
                    "positif": ("circle-plus", "#bbbbbb", "Positif"),
                    "negatif": ("circle-minus", "#666666", "Négatif"),
                    "neutre": ("circle", "#555555", "Neutre"),
                }
                icon_name, icon_color, tooltip_val = icone_map.get(valence, ("circle", "#555555", "Neutre"))
                item.setToolTip(f"{tag} — {tooltip_val}")

                # Label pour l'icône SVG
                lbl_icon = QLabel()
                lbl_icon.setFixedSize(14, 14)
                icon = self.parent_viewer.fa_svg_icon(icon_name, size=14, color=icon_color)
                if icon and not icon.isNull():
                    lbl_icon.setPixmap(icon.pixmap(14, 14))
                layout.addWidget(lbl_icon)
            else:
                item.setToolTip(tag)

            widget.setStyleSheet("background: transparent;")
            self._tag_list.addItem(item)
            self._tag_list.setItemWidget(item, widget)

        self._tag_list.repaint()
        self._tag_list.update()

        # Mise à jour de l'ensemble de sélection
        self._selected_tags_set = prev_selected & set(tag_counts.keys())
        self._active_tags = [t for t in self._active_tags if t in self._selected_tags_set]

        # Précalcul des comptages pour les tooltips des filtres
        pv = self.parent_viewer
        all_files = getattr(pv, 'all_video_files', [])
        self._filter_counts = self._compute_filter_counts(data_store, all_files, backup_dests)
        self._update_filter_tooltips()

        # Mettre à jour les tooltips des boutons de valence
        if hasattr(self, '_valence_btns'):
            for key, btn in self._valence_btns.items():
                count_key = f"valence_{key}"
                n = self._filter_counts.get(count_key, 0)
                plural = "vidéo" if n <= 1 else "vidéos"
                btn.setProperty("tip_text", f"{n} {plural}")

        # --- CORRECTION : Activer le bouton de valence si au moins un tag existe dans le store (avant filtrage) ---
        # Activer/désactiver les boutons de valence selon qu'il existe au moins un tag
        all_tags_count = len(data_store.all_tags()) if data_store else 0
        enable_valence = all_tags_count > 0
        if hasattr(self, '_valence_btns'):
            for btn in self._valence_btns.values():
                btn.setEnabled(enable_valence)
            # Mettre à jour l'état coché des boutons selon le filtre actuel (peut être None)
            for key, btn in self._valence_btns.items():
                btn.setChecked(key == self._valence_filter)

        # --- RESTAURATION DE LA POSITION DE DÉFILEMENT ---
        scrollbar.setValue(scroll_value)
        # ------------------------------------------------

        # Mettre à jour l'état des boutons de valence
        if hasattr(self, '_valence_btns'):
            for key, btn in self._valence_btns.items():
                btn.setChecked(key == self._valence_filter if self._valence_filter is not None else False)

    def refresh_panel_only(self, data_store, backup_dests=None):
        """v7.2 : Rafraîchit le panneau de tags SANS toucher à l'affichage des vignettes.
        Utilisé après delete_tag pour que la grille ne bouge pas."""
        self.refresh(data_store, backup_dests)

    def _show_tag_context_menu(self, pos):
        from PyQt6.QtWidgets import QMenu
        item = self._tag_list.itemAt(pos)
        if item is None:
            return
        tag = item.data(Qt.ItemDataRole.UserRole)
        if not tag:
            return

        menu = QMenu(self._tag_list)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2b2b2b;
                color: white;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px 6px 10px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background-color: #0078d4;
            }
            QMenu::separator {
                height: 1px;
                background: #444;
                margin: 3px 6px;
            }
        """)

        # 1. Sous-menu Valence (en premier)
        valence_menu = menu.addMenu("Valence")
        valence_menu.setStyleSheet(menu.styleSheet())
        act_pos = valence_menu.addAction("Positif")
        act_neg = valence_menu.addAction("Négatif")
        act_neu = valence_menu.addAction("Neutre")
        valence_menu.addSeparator()
        act_none = valence_menu.addAction("Aucune")

        menu.addSeparator()

        # 2. Renommer
        act_rename = menu.addAction(f"✏️  Renommer « {tag} »")

        menu.addSeparator()

        # 3. Supprimer
        act_delete = menu.addAction(f"🗑️  Supprimer « {tag} »")

        action = menu.exec(self._tag_list.viewport().mapToGlobal(pos))

        if action == act_rename:
            self._rename_tag_dialog(tag)
        elif action == act_delete:
            self._delete_tag_confirm(tag)
        elif action == act_pos:
            self.parent_viewer._get_data_store().set_tag_valence(tag, "positif")
            self.parent_viewer._refresh_tag_panel()
        elif action == act_neg:
            self.parent_viewer._get_data_store().set_tag_valence(tag, "negatif")
            self.parent_viewer._refresh_tag_panel()
        elif action == act_neu:
            self.parent_viewer._get_data_store().set_tag_valence(tag, "neutre")
            self.parent_viewer._refresh_tag_panel()
        elif action == act_none:
            self.parent_viewer._get_data_store().set_tag_valence(tag, None)
            self.parent_viewer._refresh_tag_panel()

    def _rename_tag_dialog(self, old_tag):
        """Ouvre une boîte de dialogue pour renommer un tag."""
        from PyQt6.QtWidgets import QInputDialog
        new_tag, ok = QInputDialog.getText(
            self,
            "Renommer le tag",
            f"Nouveau nom pour le tag « {old_tag} » :",
            text=old_tag
        )
        if not ok:
            return
        new_tag = new_tag.strip().lower()
        if not new_tag:
            self.parent_viewer.status_bar.set_warning("Le nom du tag ne peut pas être vide.")
            return
        if new_tag == old_tag:
            return
        # Vérifier si le nouveau nom existe déjà
        ds = self.parent_viewer._get_data_store()
        if ds and new_tag in ds.all_tags():
            from PyQt6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self,
                "Tag existant",
                f"Le tag « {new_tag} » existe déjà.\n\n"
                f"Fusionner « {old_tag} » dans « {new_tag} » ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.parent_viewer.rename_tag(old_tag, new_tag)

    def _delete_tag_confirm(self, tag):
        """Demande confirmation puis supprime le tag. L'affichage des vignettes ne bouge pas."""
        from PyQt6.QtWidgets import QMessageBox
        ds = self.parent_viewer._get_data_store()
        count = 0
        if ds:
            count = ds.all_tags().get(tag, 0)
        plural = "vidéo" if count <= 1 else "vidéos"
        msg = (
            f"Supprimer le tag « {tag} » ?\n\n"
            f"Il est attribué à {count} {plural}.\n\n"
            f"L'affichage actuel ne changera pas — "
            f"cliquez sur un autre filtre pour le mettre à jour."
        )
        reply = QMessageBox.question(
            self,
            "Supprimer le tag",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.parent_viewer.delete_tag(tag)

    def _set_item_selected_visual(self, item, selected):
        """v7.3 : utilise la sélection Qt native (SingleSelection) pour la persistance visuelle."""
        if selected:
            item.setSelected(True)
        else:
            item.setSelected(False)

    def _handle_tag_click(self, item):
        # Réinitialiser les filtres de valence et système
        self._valence_filter = None
        if hasattr(self, '_valence_btns'):
            for btn in self._valence_btns.values():
                btn.setChecked(False)
        self._active_system = "all"
        for k, btn in self._sys_btns.items():
            btn.setChecked(k == "all")
        # Vider la sélection précédente
        self._tag_list.clearSelection()
        self._selected_tags_set.clear()
        # Sélectionner le tag cliqué
        tag = item.data(Qt.ItemDataRole.UserRole)
        if tag is None:
            return
        item.setSelected(True)
        self._selected_tags_set.add(tag)
        self._active_tags = [tag]
        # Émettre le filtre
        self.tag_filter_changed.emit(self._get_current_filter())
        self._update_selection_bars()

    def _update_selection_bars(self):
        """Met à jour la visibilité des barres de sélection sur tous les items."""
        for i in range(self._tag_list.count()):
            item = self._tag_list.item(i)
            tag = item.data(Qt.ItemDataRole.UserRole)
            widget = self._tag_list.itemWidget(item)
            if widget is not None:
                bar = widget.property("selection_bar")
                if bar is not None:
                    bar.setVisible(tag in self._selected_tags_set)

    def _on_system_filter(self, key):
         # Réinitialiser la valence : état = "all", mais aucun bouton coché visuellement
        self._valence_filter = None
        if hasattr(self, '_valence_btns'):
            for btn in self._valence_btns.values():
                btn.setChecked(False)   # décoche TOUS les boutons, y compris "Tous"

        # 2. Appliquer le filtre système demandé
        self._active_system = key
        # Mise à jour visuelle des boutons système : seul 'key' reste coché
        for k, btn in self._sys_btns.items():
            btn.setChecked(k == key)

        # 3. Vider toute sélection de tags et de valence
        self._selected_tags_set.clear()
        self._active_tags = []
        self._tag_list.clearSelection()

        # 4. Si le filtre est "all", on restaure le catalogue complet pour ne rien perdre
        pv = self.parent_viewer
        if pv.full_catalog:
            pv.all_video_files = list(pv.full_catalog)

        # 5. Émettre le nouveau filtre
        self.tag_filter_changed.emit(self._get_current_filter())

    def _get_current_filter(self):
        filters = []
        if self._active_tags:
            filters.extend([("tag", t) for t in self._active_tags])
        elif self._active_system is not None:
            filters.append(("system", self._active_system))
        else:
            # Aucun filtre système ni tag actif, mais valence seule possible
            # → on émet un système "all" implicite pour que _apply_tag_filter ne court-circuite pas
            filters.append(("system", "all"))
        if self._valence_filter is not None:
            filters.append(("valence", self._valence_filter))
        return filters

    def _clear_tag_selection(self):
        self._selected_tags_set.clear()
        self._active_tags = []
        self._active_system = "all"
        
        # --- Réinitialiser valence ---
        self._valence_filter = None
        if hasattr(self, '_valence_btns'):
            for btn in self._valence_btns.values():
                btn.setChecked(False)
        # ---------------------------

        for k, btn in self._sys_btns.items():
            btn.setChecked(k == "all")
        self.tag_filter_changed.emit([("system", "all")])

    def _create_new_tag(self):
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QPushButton, QLabel, QHBoxLayout
        dlg = QDialog(self.parent_viewer)
        dlg.setWindowTitle("Nouveau tag")
        dlg.setFixedWidth(340)
        dlg.setStyleSheet("""
            QDialog { background-color: #1e1e1e; border: 1px solid #555; border-radius: 8px; }
            QLabel { color: #cccccc; font-size: 12px; }
            QLineEdit {
                background: #2a2a2a;
                color: white;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 13px;
            }
            QLineEdit:focus { border: 1px solid #555; outline: none; }
        """)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        lbl = QLabel("Nom du nouveau tag :")
        layout.addWidget(lbl)
        edit = QLineEdit()
        edit.setPlaceholderText("ex: action, suspense…")
        layout.addWidget(edit)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        btn_ok = QPushButton("Créer")
        btn_ok.setStyleSheet("QPushButton { background: #1a5a1a; color: white; border: none; border-radius: 4px; padding: 6px 16px; } QPushButton:hover { background: #226622; }")
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setStyleSheet("QPushButton { background: #3a3a3a; color: #cccccc; border: none; border-radius: 4px; padding: 6px 16px; } QPushButton:hover { background: #4a4a4a; }")
        btns.addStretch()
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        layout.addLayout(btns)
        btn_ok.clicked.connect(dlg.accept)
        btn_cancel.clicked.connect(dlg.reject)
        edit.returnPressed.connect(dlg.accept)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        tag = edit.text().strip().lower()
        if not tag:
            return
        ds = self.parent_viewer._get_data_store()
        if ds is not None:
            if "_global_tags" not in ds._data:
                ds._data["_global_tags"] = {}
            global_tags = ds._data["_global_tags"]
            if "tags" not in global_tags:
                global_tags["tags"] = []
            if tag not in global_tags["tags"]:
                global_tags["tags"].append(tag)
                ds.save()
            self.parent_viewer._refresh_tag_panel()
            self.parent_viewer.status_bar.set_success(f"Tag « {tag} » créé (0 vidéos)")

    def _set_valence_filter(self, valence):
        if valence == "all":
            self._valence_filter = None
            # Décocher tous les boutons de valence
            if hasattr(self, '_valence_btns'):
                for btn in self._valence_btns.values():
                    btn.setChecked(False)
            # Réinitialiser le filtre système à "all"
            self._active_system = "all"
            for k, btn in self._sys_btns.items():
                btn.setChecked(k == "all")
            # Effacer la sélection de tags
            self._selected_tags_set.clear()
            self._active_tags = []
            self._tag_list.clearSelection()
        elif valence in ("positif", "negatif", "neutre"):
            self._valence_filter = valence
            # Décocher les filtres système
            self._active_system = None
            for k, btn in self._sys_btns.items():
                btn.setChecked(False)
            # Effacer la sélection de tags
            self._selected_tags_set.clear()
            self._active_tags = []
            self._tag_list.clearSelection()
            # Cocher le bon bouton de valence
            if hasattr(self, '_valence_btns'):
                for key, btn in self._valence_btns.items():
                    btn.setChecked(key == valence)
        else:
            return
        # Recharger le catalogue complet
        pv = self.parent_viewer
        source = pv.full_catalog if pv.full_catalog else pv.all_video_files
        pv.all_video_files = list(source)
        # Émettre le nouveau filtre
        self.tag_filter_changed.emit(self._get_current_filter())

    # -- Drag & drop depuis les vignettes ---------------------------------
    def _list_drag_enter(self, event):
        if (self.parent_viewer.management_mode
                and (event.mimeData().hasFormat("application/x-videopath")
                     or event.mimeData().hasFormat("application/x-videopath-list"))):
            event.acceptProposedAction()
        else:
            event.ignore()

    def _list_drag_move(self, event):
        if not (self.parent_viewer.management_mode
                and (event.mimeData().hasFormat("application/x-videopath")
                     or event.mimeData().hasFormat("application/x-videopath-list"))):
            event.ignore()
            return
        event.acceptProposedAction()
        # ... (reste du code pour le hover)
        item = self._tag_list.itemAt(event.position().toPoint())
        if item is not self._drag_hover_item:
            # Réinitialiser l'ancien
            if self._drag_hover_item is not None:
                self._drag_hover_item.setBackground(
                    self._drag_hover_item.data(Qt.ItemDataRole.UserRole.value + 10)
                    or __import__('PyQt6.QtGui', fromlist=['QBrush']).QBrush()
                )
            self._drag_hover_item = item
            if item is not None:
                from PyQt6.QtGui import QBrush, QColor
                item.setData(Qt.ItemDataRole.UserRole.value + 10, item.background())
                item.setBackground(QBrush(QColor("#1a5a3a")))

    def _list_drag_leave(self, event):
        if self._drag_hover_item is not None:
            from PyQt6.QtGui import QBrush
            self._drag_hover_item.setBackground(
                self._drag_hover_item.data(Qt.ItemDataRole.UserRole.value + 10) or QBrush()
            )
            self._drag_hover_item = None

    def _list_drop(self, event):
        try:
            # Restaurer la couleur de hover
            if self._drag_hover_item is not None:
                from PyQt6.QtGui import QBrush
                self._drag_hover_item.setBackground(
                    self._drag_hover_item.data(Qt.ItemDataRole.UserRole.value + 10) or QBrush()
                )
                self._drag_hover_item = None

            mime = event.mimeData()
            video_paths = []

            if mime.hasFormat("application/x-videopath-list"):
                data = mime.data("application/x-videopath-list").data().decode('utf-8')
                video_paths = [p.strip() for p in data.split('\n') if p.strip()]
            elif mime.hasFormat("application/x-videopath"):
                video_paths = [mime.data("application/x-videopath").data().decode('utf-8')]
            elif mime.hasText():
                video_paths = [mime.text()]


            item = self._tag_list.itemAt(event.position().toPoint())
            if item is None:
                event.ignore()
                return

            tag = item.data(Qt.ItemDataRole.UserRole)
            if not tag:
                print("[DEBUG DROP] Tag invalide")
                event.ignore()
                return

            print(f"[DEBUG DROP] tag cible : {tag}")

            ds = self.parent_viewer._get_data_store()
            if ds and tag:
                count = 0
                for path in video_paths:
                    print(f"[DEBUG DROP] traitement de : {path}")
                    if os.path.exists(path):
                        ds.add_tag(path, tag)
                        count += 1
                    else:
                        print(f"[DEBUG DROP] FICHIER INTROUVABLE : {path}")
                self.parent_viewer._refresh_tag_panel()
                self.parent_viewer.status_bar.set_success(
                    f"🏷 Tag « {tag} » ajouté à {count} fichier(s)"
                )
                self.parent_viewer.deselect_all_thumbnails()
            event.acceptProposedAction()
        except Exception as e:
            import traceback
            QMessageBox.critical(self, "Erreur dans _list_drop", f"{e}\n\n{traceback.format_exc()}")

    # -- Drag & drop depuis les vignettes vers un tag ----------------------
    def get_tag_at(self, global_pos):
        """Retourne le tag sous la position globale, ou None."""
        local_pos = self._tag_list.viewport().mapFromGlobal(global_pos)
        item = self._tag_list.itemAt(local_pos)
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None

class VideoViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.full_catalog = []
        self._ignore_load_videos = False
        self.current_folder = None
        self.active_folder = None
        self.target_folder = None
        self.current_selected_video = None
        self.video_files = []
        self.all_video_files = []
        self.view_mode = "thumbnails"
        self.thumbnail_widgets = []
        self.row_widgets = []
        self.thumbnail_containers = []
        # self.last_target_dir = ""
        self.management_mode = False

        self.config = Config.load()
        self.vertical_mode = self.config.get("vertical_mode", False)

        # --- Résolutions disponibles ---
        self.horizontal_resolutions = ["426x240", "640x360", "854x480"]
        self.vertical_resolutions = ["240x426", "360x640", "480x854"]

        self.image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp']

        self.thumbnail_size = self.config["thumbnail_size"]
        self.preview_resolution = self.config["preview_resolution"]
        self.volume = self.config["volume"]
        self.play_on_hover = self.config["play_on_hover"]
        self.columns = self.config["columns"]
        self.target_folder = self.config["target_folder"]
        self.copy_shortcut_string = self.config["copy_shortcut"]
        self.show_quick_copy_buttons = self.config.get("show_quick_copy_buttons", False)
        self.lazy_loading = self.config.get("lazy_loading", True)

        self.sort_ascending = True   # True = A→Z, False = Z→A

        import re as _re
        def _unify_path(p): return _re.sub(r'[\\/]+', '/', p)
        self._unify_path = _unify_path

        # Le compteur de copies est désormais dans le FolderDataStore.
        self.copy_counts = {}   # gardé pour compatibilité, mais plus alimenté par la config.
        self.tooltip_font_size = self.config.get("tooltip_font_size", 100)
        # Sécurité : borner entre 50% et 200%
        if not (50 <= self.tooltip_font_size <= 250):
            self.tooltip_font_size = 100
        self.sort_date_order = None

        # -- Drag sur les checkboxes (vue Détails) -------------------------
        self._drag_check_active = False
        self._drag_check_state  = False
        self._drag_check_last   = None
        self._effective_thumb_spacing = self.THUMB_SPACING

        # -- Lazy loading : timer de chargement progressif -----------------
        self._lazy_timer = None
        self._lazy_iter  = None

        # -- Cache des valeurs audio pré-normalisation ----------------------
        self._pre_norm_cache = {}
        self.view_mode = self.config.get("view_mode", "thumbnails")
        self._audio_cache = {}
        self._pre_norm_cache = {}
        self._norm_history = {}
        self.explorer_mode = "classic"

        # -- v7.0 : tags & sauvegardes -------------------------------------
        self._data_store   = None   # FolderDataStore courant
        self._tag_filter   = [("system", "all")]
        self._backup_dests = []   # Désactivé – conservé pour compatibilité filtres
        
        self.parse_preview_resolution()        
        self.init_ui()
        self.setup_shortcuts()

        # --- Combo fantôme pour la gestion des modes (caché) ---
        self.explorer_mode_combo = QComboBox()
        self.explorer_mode_combo.addItems(["classic", "tags", "byfilm"])   # plus de "usage"
        self.explorer_mode_combo.setVisible(False)
        self.explorer_mode_combo.currentIndexChanged.connect(self._on_explorer_mode_changed)

        # Restaurer le mode sauvegardé
        saved_explorer = self.config.get("explorer_mode", "classic")
        mode_index = {"classic": 0, "tags": 1, "byfilm": 2}.get(saved_explorer, 0)
        self.explorer_mode_combo.setCurrentIndex(mode_index)
        self.explorer_mode = saved_explorer
        self._apply_explorer_mode_visibility()

        InstantTooltip.get(self).update_font_size(self.tooltip_font_size)
        # -- Event filter global pour le drag de checkboxes ----------------
        QApplication.instance().installEventFilter(self)

        # --- Initialisation du combo résolution en fonction de vertical_mode ---
        if hasattr(self, 'preview_res_combo'):
            self.preview_res_combo.blockSignals(True)
            self.preview_res_combo.clear()
            if self.vertical_mode:
                self.preview_res_combo.addItems(self.vertical_resolutions)
            else:
                self.preview_res_combo.addItems(self.horizontal_resolutions)

            # S'assurer que preview_resolution est valide pour le mode actuel
            if self.vertical_mode and self.preview_resolution not in self.vertical_resolutions:
                parts = self.preview_resolution.split('x')
                if len(parts) == 2:
                    inverted = f"{parts[1]}x{parts[0]}"
                    if inverted in self.vertical_resolutions:
                        self.preview_resolution = inverted
                    else:
                        self.preview_resolution = self.vertical_resolutions[0]
                else:
                    self.preview_resolution = self.vertical_resolutions[0]
            elif not self.vertical_mode and self.preview_resolution not in self.horizontal_resolutions:
                parts = self.preview_resolution.split('x')
                if len(parts) == 2:
                    inverted = f"{parts[1]}x{parts[0]}"
                    if inverted in self.horizontal_resolutions:
                        self.preview_resolution = inverted
                    else:
                        self.preview_resolution = self.horizontal_resolutions[0]
                else:
                    self.preview_resolution = self.horizontal_resolutions[0]

            self.preview_res_combo.setCurrentText(self.preview_resolution)
            self.preview_res_combo.blockSignals(False)

            # Mettre à jour le bouton pour qu'il soit cohérent
            if hasattr(self, 'btn_vertical'):
                self.btn_vertical.setChecked(self.vertical_mode)
                self.btn_vertical.setText("↕ Paysage" if self.vertical_mode else "↕ Portrait")        
        
        active_lang = self.config.get("active_source", "fr")
        startup_folder = self.config.get(f"folder_{active_lang}", "") or self.config.get("last_folder", "")
        if startup_folder and os.path.exists(startup_folder):
            self.current_folder = startup_folder
            ascending = self.sort_ascending
            self.folder_tree.load_folder_tree(self.current_folder, ascending)
            self._restore_active_folder()
        

        QTimer.singleShot(100, self.apply_custom_font)
    
    def clear_thumbnail_cache(self):
            """Exemple de nettoyage de cache ultra-rapide avec os.scandir"""
            cache_dir = os.path.join(os.path.expanduser("~"), ".cineblast_thumbnails")
            if not os.path.exists(cache_dir):
                return
            
            try:
                with os.scandir(cache_dir) as entries:
                    for entry in entries:
                        if entry.is_file() and entry.name.endswith('.jpg'):
                            os.remove(entry.path)
                self.status_bar.set_success("Cache des vignettes nettoyé !")
            except Exception as e:
                self.status_bar.set_error(f"Erreur nettoyage cache : {str(e)}")

    def fa_svg_icon(self, icon_name, size=16, color="white"):
        """
        Charge une icône Font Awesome au format SVG et retourne un QIcon colorisé.
        """
        import os
        from PyQt6.QtCore import QSize, Qt
        from PyQt6.QtGui import QPixmap, QIcon, QPainter, QColor
        from PyQt6.QtSvg import QSvgRenderer

        # Chemin vers le dossier des SVG solid
        script_dir = os.path.dirname(os.path.abspath(__file__))
        svg_path = os.path.join(script_dir, "icons", "solid", f"{icon_name}.svg")

        if not os.path.exists(svg_path):
            print(f"❌ Icône SVG introuvable : {svg_path}")
            return QIcon()

        renderer = QSvgRenderer(svg_path)
        if not renderer.isValid():
            print(f"❌ SVG invalide : {svg_path}")
            return QIcon()

        # Étape 1 : rendre le SVG (noir) sur un pixmap transparent
        pixmap = QPixmap(QSize(size, size))
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()

        # Étape 2 : recolorer le pixmap dans la couleur souhaitée
        colored = QPixmap(QSize(size, size))
        colored.fill(Qt.GlobalColor.transparent)

        painter2 = QPainter(colored)
        painter2.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter2.fillRect(colored.rect(), QColor(color))
        painter2.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        painter2.drawPixmap(0, 0, pixmap)
        painter2.end()

        return QIcon(colored)

    def apply_custom_font(self):
        """Applique Montserrat aux widgets concernés, avec gestion d'erreurs."""
        import os
        import traceback
        from PyQt6.QtGui import QFont, QFontDatabase

        try:
            font_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "IBMPlexSans-Medium.ttf")
            if not os.path.exists(font_path):
                print("Police Montserrat non trouvée, utilisation de la police par défaut.")
                return

            font_id = QFontDatabase.addApplicationFont(font_path)
            if font_id == -1:
                print("Échec du chargement de la police (ID -1).")
                return
            families = QFontDatabase.applicationFontFamilies(font_id)
            if not families:
                print("Aucune famille de police trouvée.")
                return
            family = families[0]

            custom_font = QFont(family)
            custom_font.setPointSize(9)
            button_font = QFont(family)
            button_font.setPointSize(8)

            # Liste des attributs à styler (nom de l'attribut, fonte)
            attr_names = [
                'folder_tree',
                'film_tree',
                'usage_tree',
                'tag_panel',
                'status_bar',
                'target_label',
                'preview_controls',
            ]
            for name in attr_names:
                if hasattr(self, name):
                    widget = getattr(self, name)
                    if widget is not None:
                        widget.setFont(custom_font)

            # Appliquer à tous les QLabel
            for label in self.findChildren(QLabel):
                try:
                    label.setFont(custom_font)
                except Exception:
                    pass

            # Appliquer aux QPushButton avec taille réduite
            for btn in self.findChildren(QPushButton):
                try:
                    btn.setFont(button_font)
                except Exception:
                    pass

            self.update()
            print("Police Montserrat appliquée avec succès.")
        except Exception as e:
            print("Erreur lors de l'application de la police personnalisée :")
            traceback.print_exc()

    def _apply_explorer_mode_visibility(self):
        """Met à jour la visibilité des panneaux selon self.explorer_mode."""
        self.folder_tree.setVisible(self.explorer_mode == "classic")
        self.tag_panel.setVisible(self.explorer_mode == "tags")
        self.film_tree.setVisible(self.explorer_mode == "byfilm")


    def _adjust_search_bar_width(self):
        """Ajuste la largeur de la barre de recherche à 75% du panneau central."""
        if hasattr(self, 'search_bar') and hasattr(self, 'center_panel'):
            center_width = self.center_panel.width()
            if center_width > 0:
                target_width = int(center_width * 0.75)
                self.search_bar.setFixedWidth(target_width)

    # ----------------------------------------------------------------------
    # NOUVEAU : sauvegarde automatique à la fermeture
    # ----------------------------------------------------------------------
    def closeEvent(self, event):
        """Sauvegarde automatique de l'état complet à la fermeture"""
        QApplication.instance().removeEventFilter(self)
        # Arrêter tout chargement progressif en cours
        if self._lazy_timer is not None:
            self._lazy_timer.stop()
            self._lazy_timer = None

        # --- NOUVEAU : sauvegarde silencieuse du fichier de configuration ---
        self.backup_data_store()
        # -------------------------------------------------------------------

        self._do_save()
        event.accept()

    def eventFilter(self, obj, event):
        """Intercepte MouseMove et MouseButtonRelease pour le drag de checkboxes."""
        etype = event.type()

        # Clic sur le fond du panneau central pour désélectionner
        if etype == QEvent.Type.MouseButtonPress and obj is self.content_widget:
            if event.button() == Qt.MouseButton.LeftButton:
                # Vérifier que le clic est bien sur le fond et non sur un widget enfant
                child = self.content_widget.childAt(event.pos())
                if child is None or child is self.content_widget:
                    self.deselect_all_thumbnails()
                    self.deselect_all_rows()
                    self.current_selected_video = None
                    # self.update_copy_button_state()
            # Ne pas consommer l'événement
            return False

        if etype == QEvent.Type.MouseMove and self._drag_check_active:
            global_pos = QCursor.pos()
            widget = QApplication.widgetAt(global_pos)
            row = self._find_row_widget(widget)
            if row is not None and row is not self._drag_check_last:
                row.set_checked(self._drag_check_state)
                self._drag_check_last = row

        elif etype == QEvent.Type.MouseButtonRelease and self._drag_check_active:
            self._drag_check_active = False

        return False  # ne pas consommer l'événement

    def _find_row_widget(self, widget):
        """Remonte la hiérarchie de widgets pour trouver le VideoTableRow parent."""
        w = widget
        while w is not None:
            if isinstance(w, VideoTableRow):
                return w
            w = w.parent()
        return None

    def _do_save(self):
        """Effectue la sauvegarde de la configuration (appelé manuellement ou à la fermeture)"""
        config = {
            "thumbnail_size": self.thumbnail_size,
            "preview_resolution": self.preview_resolution,
            "volume": self.volume,
            "play_on_hover": self.play_on_hover,
            "columns": self.columns,
            "last_folder": self.current_folder or "",
            "target_folder": self.target_folder or "",
            "copy_shortcut": self.copy_shortcut_string,
            "show_quick_copy_buttons": self.show_quick_copy_buttons,
            "lazy_loading": self.lazy_loading,
            "window_width": self.width(),
            "window_height": self.height(),
            "last_active_folder": self.config.get("last_active_folder", ""),
            "last_include_subdirs": self.config.get("last_include_subdirs", True),
            "last_root_files_only": self.config.get("last_root_files_only", False),
            "tooltip_font_size": self.tooltip_font_size,
            "view_mode": self.view_mode,
            "explorer_mode": self.explorer_mode,
            "last_tag_filter": self._tag_filter,
            "last_valence_filter": self.tag_panel._valence_filter if hasattr(self, 'tag_panel') else "all",            
            
            # --- AJOUT CRUCIAL : On empêche l'oubli de cette variable ---
            "last_target_browse_folder": self.config.get("last_target_browse_folder", ""),
            "folder_fr": self.config.get("folder_fr", ""),
            "folder_en": self.config.get("folder_en", ""),
            "active_source": self.config.get("active_source", "fr"),

            "vertical_mode": self.vertical_mode,
        }
        self.config.update(config)
        Config.save(self.config)

    def parse_preview_resolution(self):
        try:
            parts = self.preview_resolution.split('x')
            self.preview_width = int(parts[0])
            self.preview_height = int(parts[1])
        except:
            self.preview_width = 426
            self.preview_height = 240
            self.preview_resolution = "426x240"
        
    def init_ui(self):
        self.setWindowTitle("🎬 Fitness Viewer v1.0")

        saved_w = self.config.get("window_width", 0)
        saved_h = self.config.get("window_height", 0)
        if saved_w > 400 and saved_h > 300:
            self.setGeometry(50, 50, saved_w, saved_h)
            optimal_width = saved_w
        else:
            screen = QApplication.primaryScreen().geometry()
            optimal_width = min(1800, screen.width() - 100)
            optimal_height = min(950, screen.height() - 100)
            self.setGeometry(50, 50, optimal_width, optimal_height)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        main_panels = QWidget()
        main_panels_layout = QHBoxLayout(main_panels)
        main_panels_layout.setContentsMargins(0, 0, 0, 0)
        main_panels_layout.setSpacing(0)

        # === PANNEAU GAUCHE ===
        left_panel = QWidget()
        left_panel.setObjectName("left_panel")
        self.left_panel = left_panel
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.setSpacing(4)

        # --- Ligne source FR / EN ---
        source_row = QHBoxLayout()
        source_row.setSpacing(4)

        STYLE_SOURCE_ACTIVE = """
            QPushButton {
                background-color: #c86400; color: white;
                border: none; padding: 8px 0px;
                border-radius: 4px; font-weight: bold;
            }
            QPushButton:hover { background-color: #e07000; }
        """
        STYLE_SOURCE_INACTIVE = """
            QPushButton {
                background-color: #444; color: #aaa;
                border: none; padding: 8px 0px;
                border-radius: 4px; font-weight: bold;
            }
            QPushButton:hover { background-color: #5a5a5a; }
        """
        STYLE_GEAR = """
            QPushButton { background-color: #333; color: #888; border: none; border-radius: 4px; }
            QPushButton:hover { background-color: #4a4a4a; color: #ccc; }
        """

        self.btn_source_fr = QPushButton("📁  FR")
        self.btn_source_fr.setStyleSheet(STYLE_SOURCE_INACTIVE)
        self.btn_source_fr.clicked.connect(lambda: self.switch_source("fr"))

        self.btn_source_en = QPushButton("📁  EN")
        self.btn_source_en.setStyleSheet(STYLE_SOURCE_INACTIVE)
        self.btn_source_en.clicked.connect(lambda: self.switch_source("en"))

        def _fr_enter(ev):
            folder = self.config.get("folder_fr", "") or "Non défini"
            InstantTooltip.get(self).show_at(folder, ev.globalPosition().toPoint())
        def _fr_leave(ev):
            InstantTooltip.get(self).hide_tip()
        def _en_enter(ev):
            folder = self.config.get("folder_en", "") or "Non défini"
            InstantTooltip.get(self).show_at(folder, ev.globalPosition().toPoint())
        def _en_leave(ev):
            InstantTooltip.get(self).hide_tip()
        self.btn_source_fr.enterEvent = _fr_enter
        self.btn_source_fr.leaveEvent = _fr_leave
        self.btn_source_en.enterEvent = _en_enter
        self.btn_source_en.leaveEvent = _en_leave

        btn_gear_fr = QPushButton()
        btn_gear_fr.setFixedSize(26, 32)
        btn_gear_fr.setStyleSheet(STYLE_GEAR)
        btn_gear_fr.clicked.connect(lambda: self.reassign_folder("fr"))
        icon_gear_fr = self.fa_svg_icon("gear", size=13, color="#888888")
        if icon_gear_fr and not icon_gear_fr.isNull():
            btn_gear_fr.setIcon(icon_gear_fr)
            btn_gear_fr.setIconSize(QSize(13, 13))
        def _gear_fr_enter(ev):
            InstantTooltip.get(self).show_at("Redéfinir le dossier FR", ev.globalPosition().toPoint())
        def _gear_fr_leave(ev):
            InstantTooltip.get(self).hide_tip()
        btn_gear_fr.enterEvent = _gear_fr_enter
        btn_gear_fr.leaveEvent = _gear_fr_leave

        btn_gear_en = QPushButton()
        btn_gear_en.setFixedSize(26, 32)
        btn_gear_en.setStyleSheet(STYLE_GEAR)
        btn_gear_en.clicked.connect(lambda: self.reassign_folder("en"))
        icon_gear_en = self.fa_svg_icon("gear", size=13, color="#888888")
        if icon_gear_en and not icon_gear_en.isNull():
            btn_gear_en.setIcon(icon_gear_en)
            btn_gear_en.setIconSize(QSize(13, 13))
        def _gear_en_enter(ev):
            InstantTooltip.get(self).show_at("Redéfinir le dossier EN", ev.globalPosition().toPoint())
        def _gear_en_leave(ev):
            InstantTooltip.get(self).hide_tip()
        btn_gear_en.enterEvent = _gear_en_enter
        btn_gear_en.leaveEvent = _gear_en_leave

        source_row.addWidget(self.btn_source_fr, 1)
        source_row.addWidget(btn_gear_fr)
        source_row.addSpacing(8)
        source_row.addWidget(self.btn_source_en, 1)
        source_row.addWidget(btn_gear_en)

        # --- Ligne utilitaires ---
        top_row = QHBoxLayout()

        btn_new_folder = QPushButton()
        btn_new_folder.setToolTip("")

        def _new_folder_enter(ev):
            InstantTooltip.get(self).show_at("Créer un nouveau dossier dans l'explorateur", ev.globalPosition().toPoint())

        def _new_folder_leave(ev):
            InstantTooltip.get(self).hide_tip()

        btn_new_folder.enterEvent = _new_folder_enter
        btn_new_folder.leaveEvent = _new_folder_leave
        btn_new_folder.setFixedSize(32, 32)
        btn_new_folder.clicked.connect(self.create_new_folder)

        # Icône Font Awesome "folder-plus"
        icon_new_folder = self.fa_svg_icon("folder-plus", size=14, color="#cccccc")
        if icon_new_folder and not icon_new_folder.isNull():
            btn_new_folder.setIcon(icon_new_folder)
            btn_new_folder.setIconSize(QSize(14, 14))

        btn_new_folder.setStyleSheet("""
            QPushButton { 
                background-color: #444; 
                border: none; 
                border-radius: 4px; 
            }
            QPushButton:hover { 
                background-color: #5a5a5a; 
            }
        """)
        top_row.addWidget(btn_new_folder)

        btn_refresh = QPushButton()
        btn_refresh.setToolTip("")

        def _refresh_enter(ev):
            InstantTooltip.get(self).show_at("Rafraîchir l'explorateur", ev.globalPosition().toPoint())

        def _refresh_leave(ev):
            InstantTooltip.get(self).hide_tip()

        btn_refresh.enterEvent = _refresh_enter
        btn_refresh.leaveEvent = _refresh_leave
        btn_refresh.setFixedSize(32, 32)          # ajustement pour une icône propre
        btn_refresh.clicked.connect(self.refresh_folder_tree)

        # Icône Font Awesome "arrows-rotate"
        icon_refresh = self.fa_svg_icon("arrows-rotate", size=14, color="#cccccc")
        if icon_refresh and not icon_refresh.isNull():
            btn_refresh.setIcon(icon_refresh)
            btn_refresh.setIconSize(QSize(14, 14))

        btn_refresh.setStyleSheet("""
            QPushButton { 
                background-color: #444; 
                border: none; 
                border-radius: 4px; 
            }
            QPushButton:hover { 
                background-color: #5a5a5a; 
            }
        """)
        top_row.addWidget(btn_refresh)        

        # --- Ligne de mode d'exploration ---
        explorer_row = QHBoxLayout()
        explorer_row.setSpacing(4)

        # Bouton icône "œil" — non cliquable, décoratif
        btn_eye = QPushButton()
        btn_eye.setFixedSize(28, 28)
        btn_eye.setEnabled(True)
        btn_eye.clicked.connect(lambda: None)
        btn_eye.setCursor(Qt.CursorShape.ArrowCursor)
        icon_eye = self.fa_svg_icon("eye", size=16, color="#cccccc")
        if icon_eye and not icon_eye.isNull():
            btn_eye.setIcon(icon_eye)
            btn_eye.setIconSize(QSize(16, 16))
        btn_eye.setStyleSheet("""QPushButton { 
                                    background-color: #777777; 
                                    color: #ccc; 
                                    border: none; 
                                    border-radius: 4px; 
                                    font-size: 11px; 
                                    padding: 5px 8px; } 
                                QPushButton:hover { 
                                    background-color: #777777; 
                              }""")
        
        btn_eye.setToolTip("")

        def _eye_enter(event):
            InstantTooltip.get(self).show_at("Choix de vue", event.globalPosition().toPoint())

        def _eye_leave(event):
            InstantTooltip.get(self).hide_tip()

        btn_eye.enterEvent = _eye_enter
        btn_eye.leaveEvent = _eye_leave
        explorer_row.addWidget(btn_eye)

        # Les 4 boutons de vue
        view_definitions = [
            ("Classique", 0),
            ("Tags",      1),
            ("Films",     2),
        ]
        self._explorer_btns = {}
        btn_style_active   = """QPushButton { 
                                    background-color: #0078d4; 
                                    color: white; 
                                    border: none; 
                                    border-radius: 4px; 
                                    font-size: 11px; font-weight: bold; padding: 5px 8px; }"""
        btn_style_inactive = """QPushButton { 
                                    background-color: #444; 
                                    color: #ccc; 
                                    border: none; 
                                    border-radius: 4px; 
                                    font-size: 11px; padding: 5px 8px; } 
                                QPushButton:hover { 
                                    background-color: #5a5a5a; 
                                }"""

        def _make_view_btn(label, index):
            btn = QPushButton(label)
            btn.setToolTip("")
            btn.setStyleSheet(btn_style_inactive)
            def _clicked():
                self.explorer_mode_combo.setCurrentIndex(index)
                for i, b in self._explorer_btns.items():
                    b.setStyleSheet(btn_style_active if i == index else btn_style_inactive)
            btn.clicked.connect(_clicked)
            return btn

        for label, idx in view_definitions:
            btn = _make_view_btn(label, idx)
            self._explorer_btns[idx] = btn
            explorer_row.addWidget(btn, 1)

        # Activer le premier bouton par défaut
        self._explorer_btns[0].setStyleSheet(btn_style_active) 
        

        # Bouton de tri A→Z / Z→A
        self.btn_sort = QPushButton()
        self.btn_sort.setToolTip("")  # désactive le tooltip natif

        def _btn_sort_enter(event):
            # Le texte s'adapte automatiquement à l'ordre de tri actuel
            tip = "Tri A → Z" if self.sort_ascending else "Tri Z → A"
            InstantTooltip.get(self).show_at(tip, event.globalPosition().toPoint())

        def _btn_sort_leave(event):
            InstantTooltip.get(self).hide_tip()

        self.btn_sort.enterEvent = _btn_sort_enter
        self.btn_sort.leaveEvent = _btn_sort_leave
        
        self.btn_sort.setFixedSize(32, 32)
        self.btn_sort.clicked.connect(self.toggle_sort_order)

        icon_sort = self.fa_svg_icon("arrow-down-a-z", size=14, color="#cccccc")
        if icon_sort and not icon_sort.isNull():
            self.btn_sort.setIcon(icon_sort)
            self.btn_sort.setIconSize(QSize(14, 14))

        self.btn_sort.setStyleSheet("""
            QPushButton {
                background-color: #444;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
            }
        """)

        top_row.addWidget(self.btn_sort)
        left_layout.addLayout(source_row)
        self._update_source_buttons()
        left_layout.addLayout(top_row)
        left_layout.addLayout(explorer_row)
        
        # --------------------------------------------------------------------

        self.folder_tree = FolderTreeWidget(self)
        left_layout.addWidget(self.folder_tree)

        self.film_tree = FilmTreeWidget(self)
        self.film_tree.setVisible(False)
        left_layout.addWidget(self.film_tree)  

        # -- v7.0 : panneau de tags ----------------------------------------
        self.tag_panel = TagPanelWidget(self)
        self.tag_panel.setVisible(False)
        self.tag_panel.tag_filter_changed.connect(self._on_tag_filter_changed)
        left_layout.addWidget(self.tag_panel)

        target_group = QGroupBox("Dossier de travail (cible)")
        target_layout = QVBoxLayout(target_group)

        # --- Label cible : affiche uniquement le nom du dossier, tooltip instantané ---
        self.target_label = QLabel("Aucun dossier cible défini")
        self.target_label.setWordWrap(False)
        self.target_label.setStyleSheet("color: #ffa500; font-style: italic;")
        self.target_label.setToolTip("")                         # Désactive le tooltip natif
        self.target_label.setMouseTracking(True)

        # Installation des événements de survol pour InstantTooltip
        def _target_label_enter(event):
            if self.target_folder and os.path.exists(self.target_folder):
                tip = self.target_folder
            else:
                tip = "Aucun dossier cible défini"
            InstantTooltip.get(self).show_at(tip, event.globalPosition().toPoint())

        def _target_label_leave(event):
            InstantTooltip.get(self).hide_tip()

        self.target_label.enterEvent = _target_label_enter
        self.target_label.leaveEvent = _target_label_leave

        target_layout.addWidget(self.target_label)

        # Si un dossier cible existe déjà (chargé depuis la config), on met à jour l'affichage
        if self.target_folder and os.path.exists(self.target_folder):
            self._update_target_label_display()

        # Bouton pour choisir le dossier cible
        btn_target = QPushButton("Définir le dossier cible")
        btn_target.clicked.connect(self.choose_target_folder)
        target_layout.addWidget(btn_target)

        # Bouton de copie (supprimé, conservé uniquement pour compatibilité avec les appels)
        # self.btn_copy = None   # optionnel

        # Checkboxes (inchangées)
        self.quick_copy_checkbox = QCheckBox("Boutons rapides sous vignettes")
        self.quick_copy_checkbox.setProperty("class", "modern-checkbox")
        self.quick_copy_checkbox.setChecked(self.show_quick_copy_buttons)
        self.quick_copy_checkbox.setToolTip("Afficher/masquer les petits boutons de copie rapide sous chaque vignette")
        self.quick_copy_checkbox.stateChanged.connect(self.toggle_quick_copy_buttons)
        target_layout.addWidget(self.quick_copy_checkbox)

        self.lazy_loading_checkbox = QCheckBox("Chargement progressif")
        self.lazy_loading_checkbox.setProperty("class", "modern-checkbox")
        self.lazy_loading_checkbox.setChecked(self.lazy_loading)
        self.lazy_loading_checkbox.setToolTip(
            "Charge les vignettes par lots pour les dossiers de plus de 50 fichiers.\n"
            "L'affichage démarre immédiatement, les fichiers suivants arrivent progressivement.\n"
            "Désactiver pour charger tout d'un coup (peut figer l'interface sur les grands dossiers)."
        )        
        self.lazy_loading_checkbox.stateChanged.connect(self.toggle_lazy_loading)
        target_layout.addWidget(self.lazy_loading_checkbox)

        # --- NOUVEL EMPLACEMENT : Lecture au survol ---
        self.hover_checkbox = QCheckBox("Lecture au survol")
        self.hover_checkbox.setProperty("class", "modern-checkbox")
        self.hover_checkbox.setChecked(self.play_on_hover)
        self.hover_checkbox.stateChanged.connect(self.toggle_play_mode)
        target_layout.addWidget(self.hover_checkbox)
        # ----------------------------------------------

        target_group.setStyleSheet("""
            QGroupBox {
                color: white; border: 2px solid #ffa500;
                border-radius: 5px; margin-top: 10px; padding-top: 10px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
        """)
        left_layout.addWidget(target_group)

        btn_save_config = QPushButton("💾 Sauvegarder la configuration")
        btn_save_config.clicked.connect(self.save_settings)
        btn_save_config.setStyleSheet("""
            QPushButton {
                background-color: #5a3e8a;
                padding: 9px 10px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #7b55b8; }
        """)
        left_layout.addWidget(btn_save_config)
        
        # === PANNEAU CENTRAL ===
        center_panel = QWidget()
        center_panel.setObjectName("center_panel")
        self.center_panel = center_panel
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        
        # Barre d'outils (lignes 1 et 2)
        self.toolbar = self.create_toolbar()
        center_layout.addWidget(self.toolbar)

        # -- Barre de recherche centrée (largeur max 75%) ----------------
        # Barre de recherche centrée (largeur max 75%)
        self.search_bar = self._create_search_bar()
        self.search_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        
        search_wrapper = QWidget()
        search_wrapper.setObjectName("searchWrapper")
        search_wrapper.setStyleSheet("QWidget#searchWrapper { background-color: transparent; border: none; }")
        wrapper_layout = QHBoxLayout(search_wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(0)
        wrapper_layout.addStretch(1)
        wrapper_layout.addWidget(self.search_bar)
        wrapper_layout.addStretch(1)
        center_layout.addWidget(search_wrapper)
        center_layout.addSpacing(3)
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("scroll_area")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("background-color: #1e1e1e;")
        
        self.content_widget = QWidget()
        self.content_widget.installEventFilter(self)
        self.content_widget.setObjectName("content_widget")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.content_layout.setContentsMargins(10, 10, 10, 10)
        self.content_layout.setSpacing(10)
        self.scroll_area.setWidget(self.content_widget)
        
        center_layout.addWidget(self.scroll_area)
        
        # === PANNEAU DROIT ===
        right_panel = QWidget()
        right_panel.setObjectName("right_panel")
        self.right_panel = right_panel
        right_layout = QVBoxLayout(right_panel)

        toolbar_h = self.toolbar.sizeHint().height()
        self.right_top_spacer = QWidget()
        self.right_top_spacer.setFixedHeight(toolbar_h)
        right_layout.addWidget(self.right_top_spacer)

        preview_label = QLabel("Prévisualisation")
        preview_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #0078d4;")
        right_layout.addWidget(preview_label)
        
        self.video_widget = ClickableVideoWidget()
        self.video_widget.setMinimumSize(self.preview_width, self.preview_height)
        self.video_widget.setMaximumSize(self.preview_width + 50, self.preview_height + 50)
        self.video_widget.clicked.connect(self.toggle_play_pause)
        
        self.video_image_label = QLabel(self.video_widget)
        self.video_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_image_label.setStyleSheet("background-color: black; color: white;")
        self.video_image_label.setVisible(False)
        self.video_image_label.setGeometry(0, 0, self.video_widget.width(), self.video_widget.height())
        # Forcer le label à rester derrière les autres widgets (mais devant le fond)
        self.video_image_label.lower()

        # VLC : instance et lecteur
        self.vlc_instance = vlc.Instance("--no-plugins-cache")
        if self.vlc_instance is None:
            print("⚠️ Impossible d'initialiser VLC. Vérifiez que VLC est installé.")
            self.vlc_player = None
        else:
            self.vlc_player = self.vlc_instance.media_player_new()
            # ... attacher la fenêtre
            def _attach_vlc_window():
                if self.video_widget.winId() != 0 and self.vlc_player:
                    self.vlc_player.set_hwnd(int(self.video_widget.winId()))
                    # Désactiver la capture des entrées souris/clavier par VLC
                    self.vlc_player.video_set_mouse_input(False)
                    self.vlc_player.video_set_key_input(False)
                else:
                    QTimer.singleShot(50, _attach_vlc_window)
            QTimer.singleShot(0, _attach_vlc_window)
       
        right_layout.addWidget(self.video_widget)
        
        self.preview_controls = self.create_preview_controls()
        right_layout.addWidget(self.preview_controls)
        
        # --- Pousse tout vers le bas de la colonne de droite ---
        right_layout.addStretch()
       
        main_panels_layout.addWidget(left_panel)
        main_panels_layout.addWidget(center_panel)
        main_panels_layout.addWidget(right_panel)

        main_layout.addWidget(main_panels)

        self.status_bar = StatusBar()

        # Programmer l'installation de l'icône info (après chargement complet)
        self._setup_status_info_icon()

        main_layout.addWidget(self.status_bar)

        # Appliquer les largeurs calculées après construction de l'UI
        QTimer.singleShot(0, self._recalc_layout)
        QTimer.singleShot(10, self._adjust_search_bar_width)

        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e1e; }
            QLabel { color: white; }             
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                padding: 8px 15px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #1084d8; }
            QPushButton:pressed { background-color: #006cc1; }
            QComboBox, QSpinBox {
                background-color: #2b2b2b;
                color: white;
                border: 1px solid #555;
                padding: 5px;
                border-radius: 3px;
            }
            /* --- Classe pour les checkboxes modernes (style Lecture au survol) --- */
            QCheckBox.modern-checkbox {
                color: white;
                spacing: 8px;
            }
            QCheckBox.modern-checkbox::indicator {
                width: 17px;
                height: 17px;
                border-radius: 4px;
                border: 2px solid #777;
                background-color: #1e1e1e;
            }
            QCheckBox.modern-checkbox::indicator:unchecked:hover {
                border: 2px solid #0078d4;
                background-color: #1a2a3a;
            }
            QCheckBox.modern-checkbox::indicator:checked {
                border: 2px solid #0078d4;
                background-color: #0078d4;
            }
            QCheckBox.modern-checkbox::indicator:checked:hover {
                border: 2px solid #40a0ff;
                background-color: #1084d8;
            }
            /* --- Suppression des bordures et uniformisation du fond --- */
            QWidget#left_panel, QWidget#center_panel, QWidget#right_panel {
                border: none;
                background-color: #1e1e1e;
            }
            QScrollArea#scroll_area {
                border: none;
                background-color: #1e1e1e;
            }
            QWidget#content_widget {
                background-color: #1e1e1e;
            }

            QScrollArea#scroll_area {
                padding: 0px;
                margin: 0px;
                border: none;
            }
            QScrollArea#scroll_area > QWidget {
                padding: 0px;
                margin: 0px;
            }
            QScrollArea#scroll_area > QWidget > QWidget {
                padding: 0px;
                margin: 0px;
            }

            QScrollBar:vertical, QScrollBar:horizontal {
                background: transparent;
                width: 6px;
                height: 6px;
                border: none;
                margin: 0;
            }
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                background: #2a2a2a;
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
                background: #5a5a5a;
            }
            QScrollBar::add-line, QScrollBar::sub-line,
            QScrollBar::add-page, QScrollBar::sub-page {
                background: transparent;
                border: none;
            }

            QToolTip {
                background-color: #2a2d3a;
                color: #e8eaf0;
                border: 1px solid #4a5270;
                border-radius: 6px;
                padding: 7px 11px;
                font-size: 12px;
                font-weight: normal;
                opacity: 240;
                        QTreeWidget {
                background-color: #1e1e1e;
                color: white;
                border: none;
            }
            QTreeWidget::item {
                height: 22px;
                padding: 2px;
            }
            QTreeWidget::item:selected {
                background-color: #0078d4;
                color: white;
            }
            QTreeWidget::item:hover {
                background-color: #4a4a4a;
                border-left: 3px solid #0078d4;
            }
            }
        """)


    def _setup_status_info_icon(self):
        """Installe l'icône d'information des dépendances dans la barre de statut."""
        if not hasattr(self, 'status_bar'):
            return

        icon = self.fa_svg_icon("circle-info", size=18, color="#888")
        if icon and not icon.isNull():
            self.status_bar.info_button.setIcon(icon)
            self.status_bar.info_button.setIconSize(QSize(18, 18))

        self.status_bar.info_button.clicked.connect(self._show_dependencies_popup)

    def _show_dependencies_popup(self):
        """Affiche une popup centrée avec la liste des dépendances (sans barre titre, texte sélectionnable)."""
        dlg = QDialog(self)
        dlg.setWindowTitle("")   # pas de titre
        dlg.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.setMinimumWidth(480)

        dlg.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                border: 1px solid #555;
                border-radius: 8px;
            }
        """)

        # Layout principal
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # En-tête avec titre et croix
        header = QHBoxLayout()
        title = QLabel("📦 Dépendances de l'application")
        title.setStyleSheet("color: white; font-size: 16px; font-weight: bold; background: transparent;")
        header.addWidget(title)
        header.addStretch()
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(28, 28)
        btn_close.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #aaa;
                border: none;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: white;
                background-color: #c0392b;
                border-radius: 4px;
            }
        """)
        btn_close.clicked.connect(dlg.accept)
        header.addWidget(btn_close)
        layout.addLayout(header)

        # Séparateur
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("QFrame { color: #444; }")
        layout.addWidget(sep)

        # Contenu (sélectionnable)
        deps_text = (
            "• <b>PyQt6</b> : pip install PyQt6<br>"
            "• <b>opencv-python</b> : pip install opencv-python<br>"
            "• <b>python-vlc</b> : pip install python-vlc<br>"
            "• <b>ffmpeg (système)</b> : À installer séparément<br>"
            "• <b>VLC (système)</b> : À installer séparément"
        )
        content = QLabel(deps_text)
        content.setStyleSheet("color: #ccc; font-size: 14px; background: transparent; border: none;")
        content.setWordWrap(False)
        # Rendre le texte sélectionnable à la souris
        content.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        content.setCursor(Qt.CursorShape.IBeamCursor)
        layout.addWidget(content)

        # Bouton Fermer en bas (optionnel)
        btn_close_bottom = QPushButton("✕ Fermer")
        btn_close_bottom.setStyleSheet("""
            QPushButton {
                background-color: #444;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #5a5a5a; }
        """)
        btn_close_bottom.clicked.connect(dlg.accept)
        layout.addWidget(btn_close_bottom, alignment=Qt.AlignmentFlag.AlignRight)

        # Centrer la popup
        dlg.adjustSize()
        geo = self.geometry()
        dlg.move(geo.center() - dlg.rect().center())
        dlg.exec()

    # ----------------------------------------------------------------------
    # POINT 2 : création de la barre de recherche
    # ----------------------------------------------------------------------
    def _create_search_bar(self):
        """Barre de recherche centrée, largeur max 75%, coins arrondis, sans icône."""
        container = QWidget()
        container.setObjectName("searchContainer")
        container.setStyleSheet("""
            QWidget#searchContainer {
                background-color: transparent;
                border: none;
            }
        """)

        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Champ de saisie avec coins arrondis
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Rechercher des vidéos…")
        self.search_input.setClearButtonEnabled(False)
        self.search_input.setObjectName("searchInput")
        self.search_input.setStyleSheet("""
            QLineEdit#searchInput {
                background-color: #2b2b2b;
                color: #e0e0e0;
                border: none;
                border-radius: 8px;
                padding: 4px 12px;
                font-size: 12px;
                selection-background-color: #0078d4;
            }
            QLineEdit#searchInput:focus {
                border: 1px solid #0078d4;
            }
        """)
        self.search_input.textChanged.connect(self._apply_search_filter)
        layout.addWidget(self.search_input)

        # Bouton effacer (visible seulement si du texte)
        self.btn_clear_search = QPushButton("✕")
        self.btn_clear_search.setObjectName("clearSearchBtn")
        self.btn_clear_search.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_search.setStyleSheet("""
            QPushButton#clearSearchBtn {
                background-color: transparent;
                color: #888;
                border: none;
                padding: 0px 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton#clearSearchBtn:hover {
                color: #e0e0e0;
            }
        """)
        self.btn_clear_search.setVisible(False)
        self.btn_clear_search.clicked.connect(self.search_input.clear)
        layout.addWidget(self.btn_clear_search)

        # Compteur de résultats
        self.lbl_search_count = QLabel("")
        self.lbl_search_count.setObjectName("searchCount")
        self.lbl_search_count.setStyleSheet("""
            QLabel#searchCount {
                color: #888;
                font-size: 11px;
                background: transparent;
                min-width: 60px;
                padding-right: 8px;
            }
        """)
        self.lbl_search_count.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.lbl_search_count)

        return container

    # ----------------------------------------------------------------------
    # POINT 2 : logique de filtrage
    # ----------------------------------------------------------------------
    def _apply_search_filter(self, text: str):
        """
        Filtre self.video_files à partir de self.all_video_files selon le texte.
        Recherche insensible à la casse dans le nom du fichier (sans extension).
        Un mot partiel suffit (ex: "dra" trouve "dragon").
        Plusieurs mots séparés par des espaces = ET logique.
        """
        # Afficher/masquer le bouton ?
        self.btn_clear_search.setVisible(bool(text))

        if not text.strip():
            # Pas de filtre : afficher tout
            self.video_files = list(self.all_video_files)
            self.lbl_search_count.setText("")
        else:
            # Normalisation : minuscules, accents conservés (suffisant pour la recherche)
            keywords = text.lower().split()
            filtered = []
            for path in self.all_video_files:
                # On cherche dans le nom de fichier sans extension, en minuscules
                name = os.path.splitext(os.path.basename(path))[0].lower()
                # Tous les mots doivent être présents (ET logique)
                if all(kw in name for kw in keywords):
                    filtered.append(path)
            self.video_files = filtered
            total = len(self.all_video_files)
            found = len(filtered)
            color = "#28a745" if found > 0 else "#dc3545"
            self.lbl_search_count.setText(
                f'<span style="color:{color};">{found}</span>'
                f'<span style="color:#666;"> / {total}</span>'
            )

        self.display_videos()

    def create_toolbar(self):
        """Barre d'outils : 5 sections côte à côte"""
        toolbar = QWidget()
        toolbar.setStyleSheet("QWidget { background-color: #1e1e1e; }")

        outer = QHBoxLayout(toolbar)
        outer.setContentsMargins(6, 4, 6, 4)
        outer.setSpacing(0)

        def make_vsep():
            w = QWidget()
            wl = QHBoxLayout(w)
            wl.setContentsMargins(3, 0, 3, 0)
            wl.setSpacing(0)
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.VLine)
            sep.setStyleSheet("QFrame { color: #555; }")
            wl.addWidget(sep)
            return w

        def make_section(rows, stretch=False):
            w = QWidget()
            vl = QVBoxLayout(w)
            vl.setContentsMargins(8, 2, 8, 2)
            vl.setSpacing(4)
            for row_items in rows:
                rw = QWidget()
                rl = QHBoxLayout(rw)
                rl.setContentsMargins(0, 0, 0, 0)
                rl.setSpacing(6)
                for item in row_items:
                    if item is None:
                        rl.addStretch()
                    else:
                        rl.addWidget(item)
                if not stretch:
                    rl.addStretch()
                vl.addWidget(rw)
            return w, stretch

        def expanding_btn(text, **kwargs):
            from PyQt6.QtWidgets import QSizePolicy
            btn = QPushButton(text)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            return btn

        # SECTION 1
        self.btn_management_mode = expanding_btn("📂 Mode Gestion")
        self.btn_management_mode.setCheckable(True)
        self.btn_management_mode.setChecked(False)
        self.btn_management_mode.setToolTip("Activer le mode Gestion pour déplacer les fichiers ou glisser vers un tag")
        self.btn_management_mode.clicked.connect(self.toggle_management_mode)
        self.btn_management_mode.setStyleSheet("""
            QPushButton { background-color: #444; padding: 7px 14px; }
            QPushButton:hover { background-color: #666; }
            QPushButton:checked { background-color: #ff8800; font-weight: bold; }
            QPushButton:checked:hover { background-color: #ffa500; }
        """)

        self.btn_tag_selection = expanding_btn("🏷 Tagger")
        self.btn_tag_selection.setToolTip(
            "Ajouter/retirer des tags sur les vignettes sélectionnées\n"
            "Fonctionne sans Mode Gestion — sélectionnez d'abord une ou plusieurs vignettes"
        )
        self.btn_tag_selection.clicked.connect(self.open_tag_dialog)
        self.btn_tag_selection.setStyleSheet("""
            QPushButton { background-color: #3a2a5a; padding: 7px 14px; }
            QPushButton:hover { background-color: #5a3a8a; }
            QPushButton:disabled { background-color: #333; color: #666; }
        """)     

        s1, s1_stretch = make_section(
            [[self.btn_management_mode, self.btn_tag_selection], []],
            stretch=True
        )

        # SECTION 2
        # Bouton Vue vignettes
        self.btn_thumb_view = QPushButton()
        self.btn_thumb_view.setToolTip("Vue vignettes")
        self.btn_thumb_view.setCheckable(True)
        self.btn_thumb_view.setFixedSize(30, 30)
        icon_thumb = self.fa_svg_icon("photo-film", size=16, color="#cccccc")
        if icon_thumb and not icon_thumb.isNull():
            self.btn_thumb_view.setIcon(icon_thumb)
            self.btn_thumb_view.setIconSize(QSize(16, 16))
        self.btn_thumb_view.setStyleSheet("""
            QPushButton {
                background-color: #444;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
            }
            QPushButton:checked {
                background-color: #0078d4;
            }
        """)
        self.btn_thumb_view.clicked.connect(lambda: self.change_view_mode(0))

        # Bouton Vue détails
        self.btn_details_view = QPushButton()
        self.btn_details_view.setToolTip("Vue détails")
        self.btn_details_view.setCheckable(True)
        self.btn_details_view.setFixedSize(30, 30)
        icon_details = self.fa_svg_icon("list", size=16, color="#cccccc")
        if icon_details and not icon_details.isNull():
            self.btn_details_view.setIcon(icon_details)
            self.btn_details_view.setIconSize(QSize(16, 16))
        self.btn_details_view.setStyleSheet(self.btn_thumb_view.styleSheet())
        self.btn_details_view.clicked.connect(lambda: self.change_view_mode(1))

        # Initialiser l'état des boutons selon le mode actuel
        self.btn_thumb_view.setChecked(self.view_mode == "thumbnails")
        self.btn_details_view.setChecked(self.view_mode == "details")

        lbl_taille = QLabel("Taille:")
        self.thumb_size_combo = QComboBox()
        self.thumb_size_combo.addItems(["100 px", "150 px", "200 px", "250 px"])
        sizes = [100, 150, 200, 250]
        self.thumb_size_combo.setCurrentIndex(
            sizes.index(self.thumbnail_size) if self.thumbnail_size in sizes else 2
        )
        self.thumb_size_combo.currentIndexChanged.connect(self.change_thumbnail_size)

        lbl_col = QLabel("Colonnes:")
        self.columns_combo = QComboBox()
        self.columns_combo.addItems(["3", "4", "5", "6"])
        self.columns_combo.setCurrentIndex(self.columns - 3)
        self.columns_combo.currentIndexChanged.connect(self.change_columns)

        lbl_tt = QLabel()
        lbl_tt.setToolTip("Taille de l'infobulle")
        icon_text_height = self.fa_svg_icon("text-height", size=16, color="#cccccc")
        if icon_text_height and not icon_text_height.isNull():
            lbl_tt.setPixmap(icon_text_height.pixmap(16, 16))

        self.tooltip_size_combo = QComboBox()
        tooltip_sizes = [100, 110, 120, 130, 140, 150, 160, 170, 180]
        self.tooltip_size_combo.addItems([f"{s}%" for s in tooltip_sizes])
        cur_tt = self.tooltip_font_size if self.tooltip_font_size in tooltip_sizes else 100
        self.tooltip_size_combo.setCurrentIndex(tooltip_sizes.index(cur_tt))
        self.tooltip_size_combo.currentIndexChanged.connect(self.change_tooltip_size)
        self.tooltip_size_combo.setToolTip("Taille du texte des infobulles")

        s2, s2_stretch = make_section(
            [[self.btn_thumb_view, self.btn_details_view, lbl_taille, self.thumb_size_combo, lbl_col, self.columns_combo],
             [None, None, lbl_tt, self.tooltip_size_combo]],
            stretch=True
        )

        # SECTION 3
        self.btn_sort_date = expanding_btn("↕ Date d'ajout")
        self.btn_sort_date.setToolTip("Trier par date d'ajout\nClic : ↑/↓  |  Clic droit : désactiver")
        self.btn_sort_date.setStyleSheet("""
            QPushButton { background-color: #444; padding: 7px 12px; }
            QPushButton:hover { background-color: #666; }
        """)
        self.btn_sort_date.clicked.connect(self.cycle_sort_date)
        self.btn_sort_date.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.btn_sort_date.customContextMenuRequested.connect(self.disable_sort_date)

        s3, s3_stretch = make_section(
            [[self.btn_sort_date], []],
            stretch=True
        )

        # SECTION 4
        self.btn_analyze_audio = expanding_btn("🔍 Analyser le son")
        self.btn_analyze_audio.setToolTip(
            "Analyse True Peak et LUFS de tous les fichiers affichés\n"
            "via ffmpeg (EBU R128). Résultats visibles en vue Détails."
        )
        self.btn_analyze_audio.clicked.connect(self.analyze_audio_levels)
        self.btn_analyze_audio.setStyleSheet("""
            QPushButton { background-color: #444; padding: 7px 12px; }
            QPushButton:hover { background-color: #1a6a8a; }
            QPushButton:disabled { background-color: #333; color: #666; }
        """)

        # Combo de sélection de la cible de normalisation
        # Chaque entrée : (label affiché, LUFS cible, True Peak cible)
        self._norm_presets = [
            # Presets codec original
            ("Standard   -1.0 dB / -16 LUFS  [original]", -16.0, -1.0, False),
            ("Dynamique  -1.0 dB / -14 LUFS  [original]", -14.0, -1.0, False),
            ("Percutant  -0.5 dB / -12 LUFS  [original]", -12.0, -0.5, False),
            ("Discret    -1.0 dB / -23 LUFS  [original]", -23.0, -1.0, False),
            # Presets PCM (qualité maximale)
            ("Standard   -1.0 dB / -16 LUFS  [PCM]", -16.0, -1.0, True),
            ("Dynamique  -1.0 dB / -14 LUFS  [PCM]", -14.0, -1.0, True),
            ("Percutant  -0.5 dB / -12 LUFS  [PCM]", -12.0, -0.5, True),
            ("Discret    -1.0 dB / -23 LUFS  [PCM]", -23.0, -1.0, True),
        ]

        self.norm_target_combo = QComboBox()
        for i, (label, lufs, tp, use_pcm) in enumerate(self._norm_presets):
            self.norm_target_combo.addItem(label)
            self.norm_target_combo.setItemData(i, (lufs, tp, use_pcm))
            
        # Ajouter un séparateur visuel entre les deux groupes (après les 3 premiers)
        self.norm_target_combo.insertSeparator(4)

        self.norm_target_combo.setToolTip(
            "Sélectionner la cible de normalisation\n"
            "Standard : référence broadcast/web (\u221216 LUFS)\n"
            "Dynamique : plus présent, streaming (\u221214 LUFS)\n"
            "Percutant : très fort, limite clip (\u221212 LUFS)"
        )
        self.norm_target_combo.setStyleSheet("""
            QComboBox {
                background-color: #333;
                color: #ddd;
                border: 1px solid #555;
                padding: 4px 6px;
                border-radius: 3px;
                font-size: 11px;
            }
            QComboBox:hover { border-color: #8a5aaa; }
            QComboBox::drop-down { border: none; width: 18px; }
            QComboBox QAbstractItemView {
                background-color: #2b2b2b;
                color: #ddd;
                selection-background-color: #5a3a8a;
            }
        """)

        self.btn_normalize_audio = QPushButton("🔊 Normaliser")
        self.btn_normalize_audio.setToolTip(
            "Normalise le volume des fichiers sélectionnés (ou tous si rien n'est coché)\n"
            "selon la cible choisie dans le menu.\n"
            "La vidéo est copiée à l'identique, seul l'audio est modifié.\n"
            "Un backup est créé dans .normalized_backup/ pour pouvoir annuler."
        )
        self.btn_normalize_audio.clicked.connect(self.normalize_audio)
        self.btn_normalize_audio.setStyleSheet("""
            QPushButton { background-color: #444; padding: 5px 10px; font-size: 11px; border-radius: 3px; }
            QPushButton:hover { background-color: #6a3a8a; }
            QPushButton:disabled { background-color: #333; color: #666; }
        """)

        self.btn_revert_normalization = expanding_btn("\u21a9 Annuler normalisation")
        self.btn_revert_normalization.setToolTip(
            "Restaure les fichiers sélectionnés (ou tous si rien n'est coché)\n"
            "depuis les backups dans .normalized_backup/\n"
            "Uniquement disponible si des backups existent."
        )
        self.btn_revert_normalization.clicked.connect(self.revert_normalization)
        self.btn_revert_normalization.setStyleSheet("""
            QPushButton { background-color: #444; padding: 7px 12px; }
            QPushButton:hover { background-color: #8a4a1a; }
            QPushButton:disabled { background-color: #333; color: #666; }
        """)

        self.btn_purge_backups = expanding_btn("\U0001f5d1 Purger les backups")
        self.btn_purge_backups.setToolTip(
            "Supprime définitivement les backups des fichiers sélectionnés\n"
            "(ou tous les backups affichés si rien n'est coché).\n"
            "⚠ Après purge, la réversion devient impossible :\n"
            "les fichiers normalisés deviennent les seules versions disponibles."
        )
        self.btn_purge_backups.clicked.connect(self.purge_backups)
        self.btn_purge_backups.setStyleSheet("""
            QPushButton { background-color: #444; padding: 7px 12px; }
            QPushButton:hover { background-color: #7a1a1a; }
            QPushButton:disabled { background-color: #333; color: #666; }
        """)

        s4, s4_stretch = make_section(
            [[self.btn_analyze_audio],
             [self.norm_target_combo, self.btn_normalize_audio],
             [self.btn_revert_normalization, self.btn_purge_backups]],
            stretch=True
        )

        # SECTION 5
        lbl_shortcut = QLabel("Copie:")
        lbl_shortcut.setMouseTracking(True)
        lbl_shortcut.setToolTip("")  # désactive le tooltip Qt natif
        _tip_text_copie = "Raccourci clavier pour copier la sélection\nvers le dossier de travail"

        def _lbl_shortcut_enter(ev, _w=lbl_shortcut):
            tip = InstantTooltip.get(self)
            tip.show_at(_tip_text_copie, ev.globalPosition().toPoint())
        def _lbl_shortcut_leave(ev):
            InstantTooltip.get(self).hide_tip()

        lbl_shortcut.enterEvent = _lbl_shortcut_enter
        lbl_shortcut.leaveEvent = _lbl_shortcut_leave

        self.shortcut_edit = QKeySequenceEdit()
        self.shortcut_edit.setKeySequence(QKeySequence(self.copy_shortcut_string))
        self.shortcut_edit.keySequenceChanged.connect(self.update_copy_shortcut)
        self.shortcut_edit.setFixedWidth(100)
        self.shortcut_edit.setToolTip("")  # désactive le tooltip Qt natif (lent)
        self.shortcut_edit.setMouseTracking(True)

        def _edit_enter(ev, _w=self.shortcut_edit):
            tip = InstantTooltip.get(self)
            tip.show_at(_tip_text_copie, ev.globalPosition().toPoint())
        def _edit_leave(ev):
            InstantTooltip.get(self).hide_tip()

        self.shortcut_edit.enterEvent = _edit_enter
        self.shortcut_edit.leaveEvent = _edit_leave

        btn_clear_cache = QPushButton()
        btn_clear_cache.setToolTip("")
        btn_clear_cache.setFixedSize(32, 32)
        btn_clear_cache.setCursor(Qt.CursorShape.PointingHandCursor)

        icon_cache = self.fa_svg_icon("glass-water", size=14, color="#cccccc")
        if icon_cache and not icon_cache.isNull():
            btn_clear_cache.setIcon(icon_cache)
            btn_clear_cache.setIconSize(QSize(14, 14))

        btn_clear_cache.setStyleSheet("""
            QPushButton { background-color: #444; border: none; border-radius: 4px; }
            QPushButton:hover { background-color: #5a5a5a; }
        """)

        def _cache_enter(ev):
            InstantTooltip.get(self).show_at(
                "Rafraîchir le cache des vignettes\nMise à jour des images",
                ev.globalPosition().toPoint()
            )
        def _cache_leave(ev):
            InstantTooltip.get(self).hide_tip()

        btn_clear_cache.enterEvent = _cache_enter
        btn_clear_cache.leaveEvent = _cache_leave

        def _do_clear_cache():
            self.clear_thumbnail_cache()
            if self.video_files:
                self.display_videos()

        btn_clear_cache.clicked.connect(_do_clear_cache)

        btn_refresh = QPushButton()
        btn_refresh.setToolTip("")
        btn_refresh.setFixedSize(32, 32)
        btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)

        icon_refresh_view = self.fa_svg_icon("arrows-spin", size=14, color="#cccccc")
        if icon_refresh_view and not icon_refresh_view.isNull():
            btn_refresh.setIcon(icon_refresh_view)
            btn_refresh.setIconSize(QSize(14, 14))

        btn_refresh.setStyleSheet("""
            QPushButton { background-color: #444; border: none; border-radius: 4px; }
            QPushButton:hover { background-color: #5a5a5a; }
        """)

        def _refresh_enter(ev):
            InstantTooltip.get(self).show_at(
                "Rafraîchir l'affichage\nRelit le dossier source",
                ev.globalPosition().toPoint()
            )
        def _refresh_leave(ev):
            InstantTooltip.get(self).hide_tip()

        btn_refresh.enterEvent = _refresh_enter
        btn_refresh.leaveEvent = _refresh_leave

        def _do_refresh():
            if self.explorer_mode == "films":
                self.film_tree.load_films(self.current_folder, self.sort_ascending)
            elif self.current_folder:
                include_subdirs = getattr(self, 'last_include_subdirs', True)
                root_files_only = getattr(self, 'last_root_files_only', False)
                self.load_videos_from_path(self.current_folder, include_subdirs, root_files_only)

        btn_refresh.clicked.connect(_do_refresh)

        s5, s5_stretch = make_section(
            [[lbl_shortcut, self.shortcut_edit], [btn_clear_cache, btn_refresh]],
            stretch=False
        )

        outer.addWidget(s1, 1)
        outer.addWidget(make_vsep(), 0)
        outer.addWidget(s2, 0)
        outer.addWidget(make_vsep(), 0)
        outer.addWidget(s3, 1)
        outer.addWidget(make_vsep(), 0)
        outer.addWidget(s4, 1)
        outer.addWidget(make_vsep(), 0)
        outer.addWidget(s5, 0)

        return toolbar
    
    def toggle_management_mode(self):
        self.management_mode = self.btn_management_mode.isChecked()
        if self.management_mode:
            self.vlc_player.stop()
            QApplication.processEvents()
            self.status_bar.set_warning("MODE GESTION activé — Glissez-déposez pour déplacer les fichiers")
        else:
            self.status_bar.set_info("MODE VISUALISATION — Navigation normale")
            
            # --- AJOUT : Rafraîchir l'affichage en quittant le mode gestion ---
            if self.explorer_mode == "tags":
                self._apply_tag_filter() # Recalcule les filtres, les compteurs et redessine la grille
            else:
                self.display_videos()    # Redessine simplement la grille
    
    def create_preview_controls(self):
        controls = QGroupBox("⚙️ Paramètres de prévisualisation")
        layout = QVBoxLayout(controls)
        controls.setMinimumWidth(self.preview_width)
        
        res_layout = QHBoxLayout()
        res_layout.addWidget(QLabel("📐 Résolution:"))

        self.preview_res_combo = QComboBox()
        self.preview_res_combo.blockSignals(True)   # ← BLOQUE les signaux
        
        if self.vertical_mode:
            self.preview_res_combo.addItems(self.vertical_resolutions)
        else:
            self.preview_res_combo.addItems(self.horizontal_resolutions)
        

        # S'assurer que preview_resolution est valide pour le mode actuel
        if self.vertical_mode and self.preview_resolution not in self.vertical_resolutions:
            self.preview_resolution = self.vertical_resolutions[0]
        elif not self.vertical_mode and self.preview_resolution not in self.horizontal_resolutions:
            self.preview_resolution = self.horizontal_resolutions[0]

        # Sélectionner la résolution actuelle sans déclencher de signal
        self.preview_res_combo.setCurrentText(self.preview_resolution)
        
        self.preview_res_combo.blockSignals(False)  # ← RÉACTIVE les signaux
        self.preview_res_combo.currentTextChanged.connect(self.change_preview_resolution)
        res_layout.addWidget(self.preview_res_combo)

        self.btn_vertical = QPushButton("↕ Portrait")
        self.btn_vertical.setCheckable(True)
        self.btn_vertical.setChecked(self.vertical_mode)
        self.btn_vertical.setToolTip("Basculer entre résolutions horizontales et verticales")
        self.btn_vertical.clicked.connect(self.toggle_vertical_mode)
        res_layout.addWidget(self.btn_vertical)
        layout.addLayout(res_layout)
        
        vol_layout = QHBoxLayout()
        vol_layout.addWidget(QLabel("🔊 Volume:"))
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(self.volume)
        self.volume_slider.valueChanged.connect(self.change_volume)
        vol_layout.addWidget(self.volume_slider)
        self.volume_label = QLabel(f"{self.volume}%")
        vol_layout.addWidget(self.volume_label)
        layout.addLayout(vol_layout)
        
        info_label = QLabel("💡 Cliquez sur la vidéo pour pause/play")
        info_label.setStyleSheet("color: #ffa500; font-style: italic; font-size: 11px;")
        layout.addWidget(info_label)

        win_layout = QHBoxLayout()
        win_layout.addWidget(QLabel("🖥️ Fenêtre:"))
        self.window_res_combo = QComboBox()
        self._win_presets = ["auto", "1920x1080", "1920x1200", "1280x720", "1280x800"]
        self._win_preset_labels = ["Auto", "1920×1080", "1920×1200", "1280×720", "1280×800"]

        cur_w = self.config.get("window_width", 0)
        cur_h = self.config.get("window_height", 0)
        cur_res = f"{cur_w}x{cur_h}" if cur_w and cur_h else "auto"
        is_manual = cur_res not in self._win_presets and cur_res != "auto"

        labels = self._win_preset_labels.copy()
        if is_manual:
            labels.append(f"Manuel ({cur_w}×{cur_h})")
            self._win_presets.append(cur_res)

        self.window_res_combo.addItems(labels)

        if cur_res in self._win_presets:
            self.window_res_combo.setCurrentIndex(self._win_presets.index(cur_res))
        else:
            self.window_res_combo.setCurrentIndex(0)

        self.window_res_combo.setToolTip(
            "Choisir un preset ou conserver la taille manuelle actuelle.\n"
            "La sauvegarde mémorise toujours les dimensions exactes de la fenêtre."
        )
        self.window_res_combo.currentIndexChanged.connect(self.change_window_resolution)
        win_layout.addWidget(self.window_res_combo)
        layout.addLayout(win_layout)
        
        controls.setStyleSheet("""
            QGroupBox {
                color: white;
                border: 2px solid #0078d4;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        return controls
    
    def setup_shortcuts(self):
        # Raccourci de copie existant
        if hasattr(self, 'copy_shortcut'):
            self.copy_shortcut.activated.disconnect()
        self.copy_shortcut = QShortcut(QKeySequence(self.copy_shortcut_string), self)
        self.copy_shortcut.activated.connect(self.copy_to_target)

        # NOUVEAU : barre Espace pour lecture/pause
        self.play_pause_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self.play_pause_shortcut.activated.connect(self.toggle_play_pause_safe)
    
    def update_copy_shortcut(self, key_sequence):
        self.copy_shortcut_string = key_sequence.toString()
        self.setup_shortcuts()
    
    def toggle_play_pause(self):
        if self.management_mode:
            self.status_bar.set_warning("Lecture désactivée en mode Gestion")
            return
        if self.vlc_player.is_playing():
            self.vlc_player.pause()
            self.status_bar.set_info("Lecture en pause")
        else:
            self.vlc_player.play()
            self.status_bar.set_info("Lecture en cours")

    def toggle_play_pause_safe(self):
        """Appelle toggle_play_pause uniquement si aucun champ de saisie n'a le focus."""
        focus_widget = QApplication.focusWidget()
        if focus_widget is not None:
            # On bloque l'action Espace dans les champs de texte déjà utilisés par l'appli
            if isinstance(focus_widget, (QLineEdit, QKeySequenceEdit)):
                return
        self.toggle_play_pause()
    
    def _update_source_buttons(self):
        STYLE_ACTIVE = """
            QPushButton {
                background-color: #c86400; color: white;
                border: none; padding: 8px 0px;
                border-radius: 4px; font-weight: bold;
            }
            QPushButton:hover { background-color: #e07000; }
        """
        STYLE_INACTIVE = """
            QPushButton {
                background-color: #444; color: #aaa;
                border: none; padding: 8px 0px;
                border-radius: 4px; font-weight: bold;
            }
            QPushButton:hover { background-color: #5a5a5a; }
        """
        active = self.config.get("active_source", "fr")
        self.btn_source_fr.setStyleSheet(STYLE_ACTIVE if active == "fr" else STYLE_INACTIVE)
        self.btn_source_en.setStyleSheet(STYLE_ACTIVE if active == "en" else STYLE_INACTIVE)

    def switch_source(self, lang):
        folder = self.config.get(f"folder_{lang}", "")
        if not folder or not os.path.exists(folder):
            self.status_bar.set_warning(f"Dossier {lang.upper()} non défini — cliquez sur ⚙ pour le configurer")
            return
        self.config["active_source"] = lang
        self.current_folder = folder
        self.config["last_folder"] = folder
        Config.save(self.config)
        self._update_source_buttons()
        ascending = self.sort_ascending
        self.folder_tree.load_folder_tree(folder, ascending)
        if self.explorer_mode == "byfilm":
            self.film_tree.load_films(folder, ascending)
        self.load_videos_from_path(folder, True, False)
        self.status_bar.set_info(f"Source {lang.upper()} : {os.path.basename(folder)}")

    def reassign_folder(self, lang):
        current = self.config.get(f"folder_{lang}", "") or os.path.expanduser("~")
        if not os.path.exists(current):
            current = os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(
            self, f"Choisir le dossier source {lang.upper()}", current
        )
        if folder:
            self.config[f"folder_{lang}"] = folder
            Config.save(self.config)
            self.status_bar.set_success(f"Dossier {lang.upper()} défini : {os.path.basename(folder)}")
            if self.config.get("active_source") == lang:
                self.switch_source(lang)
    
    def choose_target_folder(self):
        last_browse = self.config.get("last_target_browse_folder", "") or ""
        
        # --- MODIFICATION 1 ---
        # Si le dossier n'existe pas, on force le dossier utilisateur (Home) au lieu de "".
        # Cela empêche Qt de s'appuyer sur la mémoire de l'autre bouton.
        if not os.path.exists(last_browse):
            last_browse = os.path.expanduser("~")
            
        folder = QFileDialog.getExistingDirectory(self, "Choisir le dossier de travail (cible)", last_browse)

        if folder:
            self.target_folder = folder
            self.config["last_target_browse_folder"] = folder
            
            # --- MODIFICATION 2 ---
            # On force la sauvegarde immédiate dans le JSON pour être sûr
            # que l'app s'en souvienne au prochain clic, même s'il y a un plantage.
            Config.save(self.config)
            
            self._update_target_label_display()
            # self.update_copy_button_state()
            self.status_bar.set_success(f"Dossier cible défini : {os.path.basename(folder)}")

    def _update_target_label_display(self):
        """Met à jour le texte du label cible pour n'afficher que le nom du dossier."""
        if self.target_folder and os.path.exists(self.target_folder):
            folder_name = os.path.basename(self.target_folder)
            self.target_label.setText(f"📂 {folder_name}")
            self.target_label.setStyleSheet("color: #28a745; font-weight: bold;")
        else:
            self.target_label.setText("Aucun dossier cible défini")
            self.target_label.setStyleSheet("color: #ffa500; font-style: italic;")
    
    def update_copy_button_state(self):
        # Méthode conservée pour compatibilité, mais ne fait rien (bouton supprimé)
        pass
    
    def copy_to_target(self):
        if not self.current_selected_video:
            self.status_bar.set_warning("Aucune vidéo sélectionnée")
            return
        if not self.target_folder or not os.path.exists(self.target_folder):
            self.status_bar.set_error("Dossier cible invalide")
            return
        
        filename = os.path.basename(self.current_selected_video)
        target_path = os.path.join(self.target_folder, filename)
        
        if os.path.exists(target_path):
            reply = QMessageBox.question(self, "Fichier existant", 
                                        f"Le fichier '{filename}' existe déjà dans le dossier cible.\n\nVoulez-vous le remplacer ?",
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.No:
                self.status_bar.set_info("Copie annulée par l'utilisateur")
                return
        
        progress = QProgressDialog("Copie en cours...", "Annuler", 0, 100, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setWindowTitle("Copie de fichier")
        progress.setMinimumDuration(0)
        
        try:
            file_size = os.path.getsize(self.current_selected_video)
            
            def copy_with_progress(src, dst):
                with open(src, 'rb') as fsrc:
                    with open(dst, 'wb') as fdst:
                        copied = 0
                        while True:
                            buf = fsrc.read(1024 * 1024)
                            if not buf:
                                break
                            fdst.write(buf)
                            copied += len(buf)
                            percent = int((copied / file_size) * 100)
                            progress.setValue(percent)
                            QApplication.processEvents()
                            if progress.wasCanceled():
                                raise Exception("Copie annulée")
            
            copy_with_progress(self.current_selected_video, target_path)
            progress.setValue(100)           

            self.status_bar.set_success(f"'{filename}' copié avec succès vers {os.path.basename(self.target_folder)}")
            
        except Exception as e:
            if "annulée" in str(e):
                self.status_bar.set_warning("Copie annulée par l'utilisateur")
            else:
                self.status_bar.set_error(f"Erreur de copie : {str(e)}")
        finally:
            progress.close()
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_search_bar_width()
        # Mise à jour de la largeur max de la barre de recherche
        if hasattr(self, 'search_inner_widget'):
            self.search_inner_widget.setMaximumWidth(int(self.width() * 0.75))
        # ... le reste du code existant pour window_res_combo
        if not hasattr(self, 'window_res_combo'):
            return
        w, h = self.width(), self.height()
        cur_res = f"{w}x{h}"
        if cur_res in self._win_presets:
            idx = self._win_presets.index(cur_res)
            self.window_res_combo.blockSignals(True)
            self.window_res_combo.setCurrentIndex(idx)
            self.window_res_combo.blockSignals(False)
        else:
            manual_label = f"Manuel ({w}×{h})"
            manual_idx = None
            for i, p in enumerate(self._win_presets):
                if p not in ["auto", "1920x1080", "1920x1200", "1280x720", "1280x800"]:
                    manual_idx = i
                    break
            self.window_res_combo.blockSignals(True)
            if manual_idx is not None:
                self._win_presets[manual_idx] = cur_res
                self.window_res_combo.setItemText(manual_idx, manual_label)
                self.window_res_combo.setCurrentIndex(manual_idx)
            else:
                self._win_presets.append(cur_res)
                self.window_res_combo.addItem(manual_label)
                self.window_res_combo.setCurrentIndex(self.window_res_combo.count() - 1)
            self.window_res_combo.blockSignals(False)

    # -- Constantes de layout -----------------------------------------------
    LEFT_W         = 280   # largeur fixe panneau gauche
    THUMB_SPACING  = 10    # espacement nominal entre vignettes
    THUMB_MARGIN   = 10    # marge interne zone centrale (haut/bas/gauche/droite)
    SCROLLBAR_W    = 18    # largeur scrollbar verticale estimée
    RIGHT_PADDING  = 16    # padding interne panneau droit (left+right)

    def _right_panel_width(self):
        return self.preview_width + self.RIGHT_PADDING

    def _center_width_for_thumbs(self):
        """Largeur idéale pour N colonnes : vignettes + espacements fixes + marges + scrollbar."""
        n   = self.columns
        tsz = self.thumbnail_size
        return (n * tsz
                + (n - 1) * self.THUMB_SPACING
                + 2 * self.THUMB_MARGIN
                + self.SCROLLBAR_W)

    def _toolbar_min_width(self):
        """Largeur minimale de la toolbar (sizeHint après construction)."""
        if hasattr(self, 'toolbar'):
            sh = self.toolbar.sizeHint().width()
            return sh if sh > 100 else 700
        return 700

    def _recalc_layout(self):
        """Recalcule et applique les largeurs des trois panneaux + la fenêtre."""
        lw  = self.LEFT_W
        rw  = self._right_panel_width()
        cw_thumbs  = self._center_width_for_thumbs()
        cw_toolbar = self._toolbar_min_width()
        cw = max(cw_thumbs, cw_toolbar)

        # Mémoriser l'espacement effectif entre vignettes pour display_thumbnails
        # Si le centre est plus large que nécessaire pour les vignettes, on répartit
        if cw > cw_thumbs and self.columns > 1:
            extra = cw - (2 * self.THUMB_MARGIN + self.SCROLLBAR_W
                          + self.columns * self.thumbnail_size)
            self._effective_thumb_spacing = extra // (self.columns - 1)
        else:
            self._effective_thumb_spacing = self.THUMB_SPACING

        self.left_panel.setFixedWidth(lw)
        self.center_panel.setFixedWidth(cw)
        self.right_panel.setFixedWidth(rw)

        # Panneau droit : preview_controls cale exactement sur la largeur interne
        ctrl_w = rw - self.RIGHT_PADDING
        self.preview_controls.setFixedWidth(ctrl_w)
        self.video_widget.setFixedWidth(ctrl_w)
        self.video_image_label.setGeometry(0, 0, self.video_widget.width(), self.video_widget.height())

        screen_w = QApplication.primaryScreen().geometry().width()
        new_w = min(lw + cw + rw, screen_w - 40)

        # Autoriser explicitement le rétrécissement avant de redimensionner
        # (évite que le minimumWidth précédent bloque la réduction)
        self.setMinimumWidth(0)
        self.resize(new_w, self.height())
        self._adjust_search_bar_width()

    def change_preview_resolution(self, resolution):
        # --- Synchronisation du mode vertical ---
        if resolution in self.vertical_resolutions:
            self.vertical_mode = True
            self.btn_vertical.setChecked(True)
            self.btn_vertical.setText("↕ Paysage")
        elif resolution in self.horizontal_resolutions:
            self.vertical_mode = False
            self.btn_vertical.setChecked(False)
            self.btn_vertical.setText("↕ Portrait")
        # --- Fin synchronisation ---

        self.preview_resolution = resolution
        self.parse_preview_resolution()
        self.video_widget.setMinimumSize(self.preview_width, self.preview_height)
        self.video_widget.setMaximumSize(self.preview_width + 50, self.preview_height + 50)
        self.video_image_label.setGeometry(0, 0, self.video_widget.width(), self.video_widget.height())
        self._recalc_layout()
        self.status_bar.set_info(f"Résolution preview : {resolution}")

    def toggle_vertical_mode(self):
        self.vertical_mode = self.btn_vertical.isChecked()
        current_res = self.preview_resolution

        # Bloquer les signaux pendant la mise à jour du combo
        self.preview_res_combo.blockSignals(True)

        # Fonction pour inverser une résolution "WxH" -> "HxW"
        def invert_res(res):
            parts = res.split('x')
            if len(parts) == 2:
                return f"{parts[1]}x{parts[0]}"
            return res

        # Déterminer la nouvelle résolution en inversant les dimensions
        inverted = invert_res(current_res)
        if self.vertical_mode:
            # On veut une résolution verticale : la liste verticale doit contenir l'inversée
            if inverted in self.vertical_resolutions:
                new_res = inverted
            else:
                new_res = self.vertical_resolutions[0]
        else:
            # On veut une résolution horizontale
            if inverted in self.horizontal_resolutions:
                new_res = inverted
            else:
                new_res = self.horizontal_resolutions[0]

        # Mettre à jour le combo
        self.preview_res_combo.clear()
        if self.vertical_mode:
            self.preview_res_combo.addItems(self.vertical_resolutions)
        else:
            self.preview_res_combo.addItems(self.horizontal_resolutions)

        # Sélectionner la nouvelle résolution
        self.preview_res_combo.setCurrentText(new_res)
        self.preview_resolution = new_res

        self.preview_res_combo.blockSignals(False)

        # Appliquer la résolution manuellement (met à jour le widget vidéo et le texte du bouton)
        self.change_preview_resolution(new_res)
        self.status_bar.set_info("Mode " + ("vertical" if self.vertical_mode else "horizontal") + " activé")
            
    def load_videos_from_path(self, folder_path, include_subdirs=False, root_files_only=False):
        """Charge les vidéos d'un chemin — stocke la liste complète dans all_video_files (Optimisé v8.2 + Fix Tags)"""
        
        if self._ignore_load_videos:
            return

        video_extensions = ('.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm', '.m4v')
        image_extensions = tuple(self.image_extensions)  # on utilise la liste définie
        media_extensions = video_extensions + image_extensions
        
        self.last_loaded_params = (folder_path, include_subdirs, root_files_only)
        self.config["last_active_folder"] = folder_path
        self.config["last_include_subdirs"] = include_subdirs
        self.config["last_root_files_only"] = root_files_only
        Config.save(self.config)
        
        found = []

        # --- EXPLORATION ULTRA-RAPIDE ---
        try:
            if root_files_only:
                with os.scandir(folder_path) as entries:
                    for entry in entries:
                        if entry.is_file() and entry.name.lower().endswith(media_extensions):
                            found.append(entry.path)
                            
            elif include_subdirs:
                # Conserve ta logique d'exclusion des dossiers cachés
                for root, dirs, files in os.walk(folder_path):
                    dirs[:] = [d for d in dirs if not d.startswith('.')]
                    for file in files:
                        if file.lower().endswith(media_extensions):
                            found.append(os.path.join(root, file))
                            
            else:
                with os.scandir(folder_path) as entries:
                    for entry in entries:
                        if entry.is_file() and not entry.name.startswith('.') and entry.name.lower().endswith(video_extensions):
                            found.append(entry.path)
        except Exception as e:
            if hasattr(self, 'status_bar'):
                self.status_bar.set_error(f"Erreur d'exploration : {str(e)}")

        found.sort()

        # -- CORRECTION DU BUG DES TAGS --
        # On remplit all_video_files et video_files avec ce qu'on vient de trouver
        self.all_video_files = found
        self.video_files = list(found)

        # Sécurité cruciale : Si on est en mode sous-dossiers (nécessaire pour les tags globaux),
        # ou si full_catalog n'a jamais été initialisé, on le synchronise immédiatement.
        if include_subdirs or not getattr(self, 'full_catalog', None):
            self.full_catalog = list(found)
        # Si on charge uniquement la racine mais que full_catalog est vide, on évite qu'il reste à néant
        elif not self.full_catalog and found:
            self.full_catalog = list(found)

        # -- INITIALISATION DU DATASTORE TRADITIONNEL --
        if self.current_folder and os.path.isdir(self.current_folder):
            self._data_store = FolderDataStore(self.current_folder)
            self._data_store.import_from_global_config(
                self._audio_cache, self._norm_history, self.copy_counts
            )
        else:
            self._data_store = None

        # -- TRAITEMENT DU MODE DE VUE --
        if self.explorer_mode == "tags":
            self._refresh_tag_panel()
            self._apply_tag_filter()  # S'appliquera désormais sur un full_catalog valide !
            return

        self._tag_filter = [("system", "all")]

        # Réinitialisation propre du champ de recherche
        if hasattr(self, 'search_input'):
            self.search_input.blockSignals(True)
            self.search_input.clear()
            self.search_input.blockSignals(False)
            self.btn_clear_search.setVisible(False)
            self.lbl_search_count.setText("")

        self.display_videos()
        
        count = len(self.video_files)
        self.status_bar.set_success(f"{count} vidéo{'s' if count > 1 else ''} trouvée{'s' if count > 1 else ''}")
        
    def display_videos(self):
        """Affiche les vidéos selon le mode sélectionné"""
        # -- Annuler tout chargement progressif en cours -------------------
        if self._lazy_timer is not None:
            self._lazy_timer.stop()
            self._lazy_timer = None
            self._release_content_height()
        self._lazy_iter = None

        for i in reversed(range(self.content_layout.count())): 
            self.content_layout.itemAt(i).widget().setParent(None)
        
        self.thumbnail_widgets = []
        self.row_widgets = []
        self.thumbnail_containers = []
        self.current_selected_video = None
        self._last_checked_idx = None
        # self.update_copy_button_state()
        
        if self.view_mode == "thumbnails":
            self.display_thumbnails()
        else:
            self.display_details()
            
    # -- Constantes du chargement progressif ------------------------------
    LAZY_THRESHOLD   = 50    # nbre de fichiers au-delà duquel le lazy loading s'active
    LAZY_FIRST_BATCH = 12    # vignettes affichées immédiatement (˜ 3 lignes × 4 cols)
    LAZY_BATCH_SIZE  = 8     # vignettes ajoutées à chaque tick
    LAZY_INTERVAL_MS = 30    # délai entre chaque lot (ms)

    def _thumb_row_height(self):
        """Hauteur d'une ligne de vignettes (vignette + éventuel bouton rapide + espacement)."""
        h = int(self.thumbnail_size * 3 / 4)   # hauteur vignette ratio 4:3
        if self.show_quick_copy_buttons:
            h += 16 + 2                         # bouton rapide + spacing interne
        return h + self.THUMB_SPACING           # espacement entre lignes

    def _preallocate_content_height(self, n_files, row_height, extra=0):
        """
        Fixe la hauteur minimale du content_widget avant le chargement progressif
        pour éviter que Qt redistribue l'espace à chaque ajout de ligne.
        extra : hauteur supplémentaire fixe (ex. header en mode Détails).
        """
        import math
        n_rows = math.ceil(n_files / self.columns)
        total_h = (n_rows * row_height
                   + 2 * self.THUMB_MARGIN
                   + extra)
        self.content_widget.setMinimumHeight(total_h)

    def _release_content_height(self):
        """Relâche la contrainte de hauteur une fois le chargement terminé."""
        self.content_widget.setMinimumHeight(0)

    def display_thumbnails(self):
        sorted_files = self._get_sorted_video_files()
        spacing      = getattr(self, '_effective_thumb_spacing', self.THUMB_SPACING)
        use_lazy     = (self.lazy_loading and len(sorted_files) > self.LAZY_THRESHOLD)

        self._lazy_current_row_widget = None
        self._lazy_current_row_layout = None
        self._lazy_col_idx = 0

        def _append_one(video_path):
            if self._lazy_col_idx % self.columns == 0:
                rw = QWidget()
                rl = QHBoxLayout(rw)
                rl.setContentsMargins(0, 0, 0, 0)
                rl.setSpacing(spacing)
                rl.setAlignment(Qt.AlignmentFlag.AlignLeft)
                self.content_layout.addWidget(rw)
                self._lazy_current_row_widget = rw
                self._lazy_current_row_layout = rl

            container = VideoThumbnailContainer(video_path, self.thumbnail_size, self)
            self.thumbnail_containers.append(container)
            self.thumbnail_widgets.append(container.thumbnail)
            self._lazy_current_row_layout.addWidget(container)
            self._lazy_col_idx += 1

        # --- Chargement immédiat (non‑lazy) ---
        if not use_lazy:
            for video_path in sorted_files:
                _append_one(video_path)
            return

        # --- Chargement progressif (lazy) ---
        self._preallocate_content_height(len(sorted_files), self._thumb_row_height())

        first_batch = sorted_files[:self.LAZY_FIRST_BATCH]
        remaining   = sorted_files[self.LAZY_FIRST_BATCH:]

        for video_path in first_batch:
            _append_one(video_path)

        if not remaining:
            self._release_content_height()
            return

        total = len(sorted_files)
        loaded_so_far = [self.LAZY_FIRST_BATCH]

        self._lazy_iter = iter(remaining)

        def _load_next_batch():
            if self._lazy_iter is None:
                return
            batch_count = 0
            try:
                while batch_count < self.LAZY_BATCH_SIZE:
                    path = next(self._lazy_iter)
                    _append_one(path)
                    loaded_so_far[0] += 1
                    batch_count += 1
                self.status_bar.set_info(
                    f"Chargement… {loaded_so_far[0]} / {total} vignettes"
                )
            except StopIteration:
                self._release_content_height()
                self._lazy_timer.stop()
                self._lazy_timer = None
                self._lazy_iter  = None
                self.status_bar.set_success(
                    f"{total} vidéo{'s' if total > 1 else ''} chargée{'s' if total > 1 else ''}"
                )

        self._lazy_timer = QTimer(self)
        self._lazy_timer.setInterval(self.LAZY_INTERVAL_MS)
        self._lazy_timer.timeout.connect(_load_next_batch)
        self._lazy_timer.start()
            
    def display_details(self):
        # Nettoyage préalable (inchangé)
        for i in reversed(range(self.content_layout.count())): 
            self.content_layout.itemAt(i).widget().setParent(None)
        self.row_widgets = []
        self.current_selected_video = None
        self._last_checked_idx = None
        # self.update_copy_button_state()

        # Création de l'en-tête (inchangé)
        header = QWidget()
        header.setFixedHeight(26)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 6, 0)
        header_layout.setSpacing(0)
        header.setStyleSheet("background-color: #222; border-bottom: 2px solid #555;")
        # ... tout le code de création de l'en-tête reste identique ...
        self.content_layout.addWidget(header)

        all_files = self._get_sorted_video_files()
        video_files = [p for p in all_files if os.path.splitext(p)[1].lower() not in self.image_extensions]
        sorted_files = video_files
        use_lazy = (self.lazy_loading and len(sorted_files) > self.LAZY_THRESHOLD)

        def _append_row(video_path):
            row = VideoTableRow(video_path, self)
            self.row_widgets.append(row)
            self.content_layout.addWidget(row)

        if not use_lazy:
            for video_path in sorted_files:
                _append_row(video_path)
            return

        # -- Pré-allouer la hauteur totale pour éviter l'effet accordéon --
        DETAIL_ROW_H = 33  # hauteur estimée d'une ligne (inclut la bordure)
        HEADER_H = 26 + self.THUMB_SPACING  # hauteur de l'en-tête + espacement
        total_h = (len(sorted_files) * DETAIL_ROW_H) + HEADER_H + 20  # marge de sécurité
        self.content_widget.setMinimumHeight(total_h)

        # Premier lot : affiché immédiatement
        total = len(sorted_files)
        first_batch = sorted_files[:self.LAZY_FIRST_BATCH]
        remaining   = sorted_files[self.LAZY_FIRST_BATCH:]

        for video_path in first_batch:
            _append_row(video_path)

        if not remaining:
            self._release_content_height()
            return

        loaded_so_far = [self.LAZY_FIRST_BATCH]
        self._lazy_iter = iter(remaining)

        def _load_next_batch():
            if self._lazy_iter is None:
                return
            batch_count = 0
            try:
                while batch_count < self.LAZY_BATCH_SIZE:
                    path = next(self._lazy_iter)
                    _append_row(path)
                    loaded_so_far[0] += 1
                    batch_count += 1
                self.status_bar.set_info(
                    f"Chargement… {loaded_so_far[0]} / {total} lignes"
                )
            except StopIteration:
                self._release_content_height()
                self._lazy_timer.stop()
                self._lazy_timer = None
                self._lazy_iter  = None
                self.status_bar.set_success(
                    f"{total} vidéo{'s' if total > 1 else ''} chargée{'s' if total > 1 else ''}"
                )

        self._lazy_timer = QTimer(self)
        self._lazy_timer.setInterval(self.LAZY_INTERVAL_MS)
        self._lazy_timer.timeout.connect(_load_next_batch)
        self._lazy_timer.start()
    
    def deselect_all_thumbnails(self):
        for thumb in self.thumbnail_widgets:
            thumb.is_selected = False
            thumb.update_style()
        # self.update_copy_button_state()
    
    def deselect_all_rows(self):
        for row in self.row_widgets:
            row.is_selected = False
            row.update_style()
        # self.update_copy_button_state()

    def _shift_click_check(self, clicked_row):
        """Shift+clic : coche/décoche toutes les lignes entre le dernier clic et celui-ci."""
        if not self.row_widgets:
            return
        # Déterminer l'état cible : inverse de l'état courant de la ligne cliquée
        new_state = not clicked_row.is_checked()
        # Trouver l'index de la dernière ligne modifiée (référence) et de la ligne cliquée
        try:
            clicked_idx = self.row_widgets.index(clicked_row)
        except ValueError:
            return
        ref_idx = getattr(self, '_last_checked_idx', None)
        clicked_row.set_checked(new_state)
        if ref_idx is not None and ref_idx != clicked_idx:
            lo, hi = sorted([ref_idx, clicked_idx])
            for row in self.row_widgets[lo:hi + 1]:
                row.set_checked(new_state)
        self._last_checked_idx = clicked_idx

    def toggle_all_checks(self):
        """Bascule les cases à cocher : décoche tout si au moins une cochée, sinon coche tout."""
        any_checked = any(row.is_checked() for row in self.row_widgets)
        new_state = not any_checked
        for row in self.row_widgets:
            row.set_checked(new_state)
            
    def play_preview(self, video_path):
        """Lance la prévisualisation (vidéo ou image)."""
        ext = os.path.splitext(video_path)[1].lower()
        if ext in self.image_extensions:
            # Afficher l'image
            self.vlc_player.stop()
            # Rendre le label visible et le widget VLC transparent (ou caché)
            self.video_image_label.setVisible(True)
            self.video_widget.setVisible(True)  # ne pas cacher, sinon le label n'est pas visible
            # Charger l'image
            pixmap = QPixmap(video_path)
            if not pixmap.isNull():
                # Redimensionner en conservant le ratio
                scaled = pixmap.scaled(self.video_widget.width(), self.video_widget.height(),
                                       Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
                self.video_image_label.setPixmap(scaled)
                self.video_image_label.setStyleSheet("background-color: black;")
            else:
                self.video_image_label.setText("❌ Image invalide")
                self.video_image_label.setStyleSheet("color: white; background-color: black; font-size: 20px;")
            self.status_bar.set_info(f"Image : {os.path.basename(video_path)}")
            return

        # Sinon, c'est une vidéo
        self.video_image_label.setVisible(False)
        self.video_widget.setVisible(True)
        self.vlc_player.stop()
        media = self.vlc_instance.media_new(video_path)
        self.vlc_player.set_media(media)
        self.vlc_player.play()
        filename = os.path.basename(video_path)
        self.status_bar.set_info(f"Lecture : {filename}")
        
    def change_view_mode(self, index):
        self.view_mode = "thumbnails" if index == 0 else "details"
        # Mettre à jour l'état des boutons (s'ils existent)
        if hasattr(self, 'btn_thumb_view'):
            self.btn_thumb_view.setChecked(self.view_mode == "thumbnails")
            self.btn_details_view.setChecked(self.view_mode == "details")
        if self.video_files:
            self.display_videos()
            
    def change_thumbnail_size(self, index):
        sizes = [100, 150, 200, 250]
        self.thumbnail_size = sizes[index]
        self._recalc_layout()
        if self.view_mode == "thumbnails" and self.video_files:
            self.display_videos()

    def change_columns(self, index):
        self.columns = index + 3
        self._recalc_layout()
        if self.view_mode == "thumbnails" and self.video_files:
            self.display_videos()
    
    def toggle_play_mode(self, state):
        self.play_on_hover = (state == Qt.CheckState.Checked.value)
        
    def change_volume(self, value):
        self.volume = value
        self.volume_label.setText(f"{value}%")
        self.vlc_player.audio_set_volume(value)

    def _on_explorer_mode_changed(self, index):
        """Slot du QComboBox de mode d'exploration : 0=classique, 1=tags, 2=par films, 3=top copies."""
        
        # Synchroniser l'état visuel des boutons
        btn_style_active   = """QPushButton { background-color: #0078d4; color: white; border: none; border-radius: 4px; font-size: 11px; font-weight: bold; padding: 5px 8px; }"""
        btn_style_inactive = """QPushButton { background-color: #444; color: #ccc; border: none; border-radius: 4px; font-size: 11px; padding: 5px 8px; } QPushButton:hover { background-color: #5a5a5a; }"""
        if hasattr(self, '_explorer_btns'):
            for i, b in self._explorer_btns.items():
                b.setStyleSheet(btn_style_active if i == index else btn_style_inactive)

        modes = ["classic", "tags", "byfilm"]
        new_mode = modes[index] if index < len(modes) else "classic"
        if new_mode == self.explorer_mode:
            return
        self.explorer_mode = new_mode

        self._apply_explorer_mode_visibility()

        if new_mode == "classic":
            self.status_bar.set_info("Vue classique activée")
        elif new_mode == "tags":
            try:
                self._ignore_load_videos = True

                # --- Dossier à charger (identique à celui de la vue classique) ---
                if hasattr(self, 'last_loaded_params'):
                    folder, include_subdirs, root_files_only = self.last_loaded_params
                else:
                    folder = self.current_folder
                    include_subdirs = True
                    root_files_only = False

                # --- RÉINITIALISER LE FILTRE À "TOUS" (comportement du basculement) ---
                self._tag_filter = [("system", "all")]
                self.tag_panel._active_system = "all"
                self.tag_panel._active_tags = []
                self.tag_panel._selected_tags_set.clear()
                
                self.tag_panel._valence_filter = "all"
                if hasattr(self.tag_panel, '_valence_btns'):
                    for key, btn in self.tag_panel._valence_btns.items():
                        btn.setChecked(key == "all")

                # --- Charger les vidéos ---
                if folder and os.path.exists(folder):
                    # Pendant tout le chargement, on empêche l'affichage automatique
                    self._ignore_load_videos = True
                    self.load_videos_from_path(folder, include_subdirs, root_files_only)
                    # On laisse _ignore_load_videos = True pour ne pas toucher aux vignettes
                else:
                    self._ignore_load_videos = False
                    return

                if folder != self.current_folder or not include_subdirs:
                    self._load_full_catalog_in_background()

                self._refresh_tag_panel()
                QTimer.singleShot(10, self.tag_panel.repaint)
                self.tag_panel.repaint()
                self.tag_panel.update()

                def apply_and_unlock():
                    # Surtout, ne pas appliquer le filtre ici !
                    if hasattr(self, 'all_video_files'):
                        count = len(self.all_video_files)
                        folder_name = os.path.basename(folder) if folder else "dossier inconnu"
                        self.status_bar.set_success(f"Dossier chargé : {folder_name} ({count} vidéos)")
                    self._ignore_load_videos = False

                QTimer.singleShot(50, apply_and_unlock)

                self.status_bar.set_info("Vue par tags activée")
            except Exception as e:
                import traceback
                QMessageBox.critical(self, "Erreur vue Tags",
                    f"Erreur lors du passage en vue Tags:\n{str(e)}\n\n{traceback.format_exc()}")
                self._ignore_load_videos = False
        elif new_mode == "byfilm":
            if self.current_folder:
                self.film_tree.load_films(self.current_folder, self.sort_ascending)
                self.status_bar.set_info("Vue par films activée")
            else:
                self.status_bar.set_warning("Aucun dossier source chargé")

    def _restore_tag_filter(self):
        saved_filter = self.config.get("last_tag_filter", [("system", "all")])
        saved_valence = self.config.get("last_valence_filter", "all")
        
        self._tag_filter = saved_filter
        if hasattr(self, 'tag_panel'):
            self.tag_panel._active_system = "all"
            self.tag_panel._active_tags = []
            for ftype, fval in saved_filter:
                if ftype == "system":
                    self.tag_panel._active_system = fval
                elif ftype == "tag":
                    self.tag_panel._active_tags.append(fval)
            
            self.tag_panel._valence_filter = saved_valence
            labels = {"all": "Tous", "positif": "Positif", "negatif": "Négatif", "neutre": "Neutre"}
            colors = {"all": "#3a3a4a", "positif": "#1E90FF", "negatif": "#FF8C00", "neutre": "#AAAAAA"}
            self.tag_panel._valence_btn.setText(f"Valence : {labels.get(saved_valence, 'Tous')}")
            self.tag_panel._valence_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {colors.get(saved_valence, '#3a3a4a')};
                    color: white;
                    border: none;
                    padding: 5px 8px;
                    text-align: left;
                    font-size: 11px;
                    border-radius: 3px;
                }}
                QPushButton:hover {{ background-color: #4a4a6a; }}
            """)
            
            for k, btn in self.tag_panel._sys_btns.items():
                btn.setChecked(k == self.tag_panel._active_system)
            
            self.tag_panel._selected_tags_set = set(self.tag_panel._active_tags)
            for i in range(self.tag_panel._tag_list.count()):
                item = self.tag_panel._tag_list.item(i)
                tag = item.data(Qt.ItemDataRole.UserRole)
                if tag in self.tag_panel._selected_tags_set:
                    item.setSelected(True)
            
            self._apply_tag_filter()

    # Gardées pour compatibilité avec d'éventuels appels internes (refresh_folder_tree etc.)
    def toggle_explorer_mode(self):
        idx = 0 if self.explorer_mode == "byfilm" else 1
        self.explorer_mode_combo.setCurrentIndex(idx)

    def toggle_usage_mode(self):
        idx = 0 if self.explorer_mode == "usage" else 2
        self.explorer_mode_combo.setCurrentIndex(idx)

    def load_video_list(self, video_paths, label=""):
        """Charge une liste préconstruite — stocke aussi dans all_video_files"""
        sorted_paths = sorted(video_paths)
        # -- Stocker la liste complète ET réinitialiser le filtre ----------
        self.all_video_files = sorted_paths
        self.video_files = list(sorted_paths)

        if hasattr(self, 'search_input'):
            self.search_input.blockSignals(True)
            self.search_input.clear()
            self.search_input.blockSignals(False)
            self.btn_clear_search.setVisible(False)
            self.lbl_search_count.setText("")
        # ------------------------------------------------------------------

        self.display_videos()
        count = len(self.video_files)
        suffix = f" — {label}" if label else ""
        self.status_bar.set_success(
            f"? {count} extrait{'s' if count > 1 else ''} trouvé{'s' if count > 1 else ''}{suffix}"
        )

    def create_new_folder(self):
        if not self.current_folder or not os.path.exists(self.current_folder):
            self.status_bar.set_warning("Aucun dossier source chargé")
            return

        selected_items = self.folder_tree.selectedItems()
        if selected_items:
            item = selected_items[0]
            parent_path = item.data(0, Qt.ItemDataRole.UserRole)
            root_files_only = item.data(0, Qt.ItemDataRole.UserRole.value + 2)
            if root_files_only or not parent_path or not os.path.isdir(parent_path):
                parent_path = self.current_folder
        else:
            parent_path = self.current_folder

        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(
            self, "Nouveau dossier",
            f"Nom du nouveau dossier\n(dans : {os.path.basename(parent_path)}) :"
        )
        if not ok or not name.strip():
            return

        name = name.strip()
        new_path = os.path.join(parent_path, name)

        if os.path.exists(new_path):
            self.status_bar.set_warning(f"Un dossier « {name} » existe déjà ici")
            return

        try:
            os.makedirs(new_path)
            self.status_bar.set_success(f"Dossier « {name} » créé")
            ascending = self.sort_ascending
            self.folder_tree.load_folder_tree(self.current_folder, ascending)
        except Exception as e:
            self.status_bar.set_error(f"Impossible de créer le dossier : {e}")

    def refresh_folder_tree(self):
        if not self.current_folder or not os.path.exists(self.current_folder):
            self.status_bar.set_warning("Aucun dossier source chargé")
            return
        ascending = self.sort_ascending
        if self.explorer_mode == "classic":
            self.folder_tree.load_folder_tree(self.current_folder, ascending)
            self.status_bar.set_info("Explorateur rafraîchi")
        elif self.explorer_mode == "byfilm":
            self.film_tree.load_films(self.current_folder, ascending)
            self.status_bar.set_info("Vue par films rafraîchie")

    def refresh_after_move(self):
        if self.current_folder and os.path.exists(self.current_folder):
            ascending = self.sort_ascending
            self.folder_tree.load_folder_tree(self.current_folder, ascending)
        
        if hasattr(self, 'last_loaded_params'):
            folder_path, include_subdirs, root_files_only = self.last_loaded_params
            if os.path.exists(folder_path):
                self.load_videos_from_path(folder_path, include_subdirs, root_files_only)

    def apply_sort_order(self):
        """Applique le tri actuel (ascendant/descendant) à l'explorateur."""
        if not self.current_folder or not os.path.exists(self.current_folder):
            return
        if self.explorer_mode == "classic":
            self.folder_tree.load_folder_tree(self.current_folder, self.sort_ascending)
        elif self.explorer_mode == "byfilm":
            self.film_tree.load_films(self.current_folder, self.sort_ascending)
        elif self.explorer_mode == "tags":
            self._refresh_tag_panel()

    def toggle_sort_order(self):
        """Bascule l'ordre de tri et rafraîchit l'affichage."""
        self.sort_ascending = not self.sort_ascending
        self._update_sort_button_icon()
        self.apply_sort_order()

    def _update_sort_button_icon(self):
        """Met à jour l'icône et le tooltip du bouton de tri selon l'état actuel."""
        if self.sort_ascending:
            icon_name = "arrow-down-a-z"
            tooltip = "Tri A → Z"
        else:
            icon_name = "arrow-down-z-a"
            tooltip = "Tri Z → A"

        icon = self.fa_svg_icon(icon_name, size=14, color="#cccccc")
        if icon and not icon.isNull():
            self.btn_sort.setIcon(icon)
            self.btn_sort.setIconSize(QSize(14, 14))
        self.btn_sort.setToolTip(tooltip)

    def change_window_resolution(self, index):
        chosen = self._win_presets[index]
        if chosen == "auto":
            screen = QApplication.primaryScreen().geometry()
            w = min(1800, screen.width() - 100)
            h = min(950, screen.height() - 100)
            self.resize(w, h)
            self.status_bar.set_info("Taille de fenêtre : automatique")
        else:
            try:
                w, h = [int(x) for x in chosen.split("x")]
                self.resize(w, h)
                self.status_bar.set_info(f"Taille de fenêtre : {w}×{h}")
            except Exception:
                pass

    def toggle_quick_copy_buttons(self, state):
        self.show_quick_copy_buttons = (state == Qt.CheckState.Checked.value)
        for container in self.thumbnail_containers:
            container.set_quick_copy_visible(self.show_quick_copy_buttons)

    def toggle_lazy_loading(self, state):
        self.lazy_loading = (state == Qt.CheckState.Checked.value)
        if self.lazy_loading:
            self.status_bar.set_info("Chargement progressif activé (dossiers > 50 fichiers)")
        else:
            self.status_bar.set_info("Chargement progressif désactivé")

    def cycle_sort_date(self):
        if self.sort_copies_order is not None:
            self.sort_copies_order = None
            self.btn_sort_copies.setText("↕ Copies")
            self.btn_sort_copies.setStyleSheet("""
                QPushButton { background-color: #444; padding: 7px 12px; }
                QPushButton:hover { background-color: #666; }
            """)
        if self.sort_date_order is None:
            self.sort_date_order = "desc"
            self.btn_sort_date.setText("↓ Date d'ajout")
            self.btn_sort_date.setStyleSheet("""
                QPushButton { background-color: #1a6a8a; padding: 7px 12px; font-weight: bold; }
                QPushButton:hover { background-color: #2288aa; }
            """)
            self.status_bar.set_info("? Tri date : plus récent en premier")
        elif self.sort_date_order == "desc":
            self.sort_date_order = "asc"
            self.btn_sort_date.setText("↑ Date d'ajout")
            self.btn_sort_date.setStyleSheet("""
                QPushButton { background-color: #1a6a8a; padding: 7px 12px; font-weight: bold; }
                QPushButton:hover { background-color: #2288aa; }
            """)
            self.status_bar.set_info("↑ Tri date : plus ancien en premier")
        else:
            self.sort_date_order = None
            self.btn_sort_date.setText("↕ Date d'ajout")
            self.btn_sort_date.setStyleSheet("""
                QPushButton { background-color: #444; padding: 7px 12px; }
                QPushButton:hover { background-color: #666; }
            """)
            self.status_bar.set_info("Tri par date désactivé")
        self.display_videos()

    def disable_sort_date(self, pos=None):
        if self.sort_date_order is not None:
            self.sort_date_order = None
            self.btn_sort_date.setText("↕ Date d'ajout")
            self.btn_sort_date.setStyleSheet("""
                QPushButton { background-color: #444; padding: 7px 12px; }
                QPushButton:hover { background-color: #666; }
            """)
            self.status_bar.set_info("Tri par date désactivé")
            self.display_videos()

    def change_tooltip_size(self, index):
        sizes = [100, 110, 120, 130, 140, 150, 160, 170, 180]
        self.tooltip_font_size = sizes[index]
        if InstantTooltip._instance is not None:
            InstantTooltip._instance.update_font_size(self.tooltip_font_size)

    def _get_sorted_video_files(self):
        files = list(self.video_files)
        if self.sort_date_order is not None:
            reverse = (self.sort_date_order == "desc")
            files = sorted(files, key=lambda p: os.path.getmtime(p), reverse=reverse)        
        return files

    def _find_tree_item_by_path(self, target_path, include_subdirs, root_files_only):
        def search(item):
            path = item.data(0, Qt.ItemDataRole.UserRole)
            item_include_subdirs = item.data(0, Qt.ItemDataRole.UserRole.value + 1)
            item_root_files_only = item.data(0, Qt.ItemDataRole.UserRole.value + 2)
            if (path == target_path and
                    bool(item_include_subdirs) == bool(include_subdirs) and
                    bool(item_root_files_only) == bool(root_files_only)):
                return item
            for i in range(item.childCount()):
                result = search(item.child(i))
                if result:
                    return result
            return None

        for i in range(self.folder_tree.topLevelItemCount()):
            result = search(self.folder_tree.topLevelItem(i))
            if result:
                return result
        return None

    def _restore_active_folder(self):
        if self.explorer_mode == "tags":
            self._ignore_load_videos = True

            # --- Déterminer le dossier à charger (avec fallbacks) ---
            folder = None
            include_subdirs = True
            root_files_only = False

            if hasattr(self, 'last_loaded_params'):
                f, inc, root_only = self.last_loaded_params
                if f and os.path.exists(f):
                    folder, include_subdirs, root_files_only = f, inc, root_only

            if not folder:
                folder = self.current_folder
                include_subdirs = True
                root_files_only = False

            if not folder:
                folder = self.config.get("last_folder", "")

            if not folder or not os.path.exists(folder):
                self._ignore_load_videos = False
                return  # On laisse l'interface vide, l'utilisateur choisira un dossier

            # --- Restaurer le filtre sauvegardé ---
            saved_filter = self.config.get("last_tag_filter", [("system", "all")])
            saved_valence = self.config.get("last_valence_filter", "all")
            self._tag_filter = saved_filter
            if hasattr(self, 'tag_panel'):
                self.tag_panel._active_system = "all"
                self.tag_panel._active_tags = []
                for ftype, fval in saved_filter:
                    if ftype == "system":
                        self.tag_panel._active_system = fval
                    elif ftype == "tag":
                        self.tag_panel._active_tags.append(fval)

                self.tag_panel._valence_filter = saved_valence
                if hasattr(self.tag_panel, '_valence_btns'):
                    for key, btn in self.tag_panel._valence_btns.items():
                        btn.setChecked(key == saved_valence)

                for k, btn in self.tag_panel._sys_btns.items():
                    btn.setChecked(k == self.tag_panel._active_system)
                self.tag_panel._selected_tags_set = set(self.tag_panel._active_tags)

            # --- Charger les vidéos ---
            self._ignore_load_videos = False
            self.load_videos_from_path(folder, include_subdirs, root_files_only)
            self._ignore_load_videos = True

            # Charger le catalogue complet en arrière-plan si nécessaire
            if folder != self.current_folder or not include_subdirs:
                self._load_full_catalog_in_background()

            self._refresh_tag_panel()

            def apply_and_unlock():
                if hasattr(self, 'tag_panel'):
                    for i in range(self.tag_panel._tag_list.count()):
                        item = self.tag_panel._tag_list.item(i)
                        tag = item.data(Qt.ItemDataRole.UserRole)
                        if tag in self.tag_panel._selected_tags_set:
                            item.setSelected(True)
                self._apply_tag_filter()
                
                # --- Mise à jour de la barre de statut ---
                if hasattr(self, 'all_video_files'):
                    count = len(self.all_video_files)
                    folder_name = os.path.basename(folder) if folder else "dossier inconnu"
                    self.status_bar.set_success(f"Dossier chargé : {folder_name} ({count} vidéos)")
                # -----------------------------------------
                
                self._ignore_load_videos = False

            QTimer.singleShot(50, apply_and_unlock)
            return

        # --- Suite pour les autres modes (inchangée) ---
        active_folder = self.config.get("last_active_folder", "")
        include_subdirs = self.config.get("last_include_subdirs", True)
        root_files_only = self.config.get("last_root_files_only", False)

        if not active_folder or not os.path.exists(active_folder):
            self.load_videos_from_path(self.current_folder, True, False)
            return

        self.load_videos_from_path(active_folder, include_subdirs, root_files_only)

        item = self._find_tree_item_by_path(active_folder, include_subdirs, root_files_only)
        if item:
            self.folder_tree.setCurrentItem(item)
            self.folder_tree.scrollToItem(item)


    # -- Historique de normalisation : lookup avec fallback par nom --------
    PRESET_ORDER = {"Standard": 0, "Dynamique": 1, "Percutant": 2}

    def _get_norm_info(self, video_path):
        """
        Retourne le dict {"preset": str, "date": str} pour ce fichier,
        ou None si aucune normalisation connue.
        Lookup : 1) chemin absolu, 2) nom de fichier unique (fallback).
        En cas de doublon sur le nom, avertit dans la status bar et retourne None.
        """
        # 1. Chemin absolu exact
        if video_path in self._norm_history:
            return self._norm_history[video_path]

        # 2. Fallback par nom de fichier
        target_name = os.path.basename(video_path)
        matches = [(k, v) for k, v in self._norm_history.items()
                   if os.path.basename(k) == target_name]
        if len(matches) == 1:
            # Migrer la clé vers le nouveau chemin
            old_key, info = matches[0]
            self._norm_history[video_path] = info
            del self._norm_history[old_key]
            return info
        if len(matches) > 1:
            self.status_bar.set_warning(
                f"⚠ Doublon détecté : « {target_name} » apparaît dans plusieurs dossiers "
                f"— historique de normalisation ignoré pour ce fichier"
            )
        return None

    def _set_norm_info(self, video_path, preset_name):
        """Enregistre/met à jour l'historique de normalisation pour un fichier."""
        from datetime import date
        self._norm_history[video_path] = {
            "preset": preset_name,
            "date": date.today().strftime("%d/%m/%Y"),
        }

    def _clear_norm_info(self, video_path):
        """Supprime l'historique de normalisation pour un fichier (après revert)."""
        self._norm_history.pop(video_path, None)

    def analyze_audio_levels(self):
        if not self.video_files:
            self.status_bar.set_warning("Aucun fichier à analyser")
            return

        import subprocess

        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self.status_bar.set_error("ffmpeg introuvable — vérifiez qu'il est installé et dans le PATH")
            return

        checked_paths = {row.video_path for row in self.row_widgets if row.is_checked()}

        all_files = list(self._get_sorted_video_files())
        # Filtrer pour ne garder que les vidéos
        all_files = [p for p in all_files if os.path.splitext(p)[1].lower() not in self.image_extensions]

        if checked_paths:
            files_to_analyze = [p for p in all_files if p in checked_paths]
            force_reanalyze = True
        else:
            files_to_analyze = [p for p in all_files if p not in self._audio_cache]
            force_reanalyze = False

        if not files_to_analyze:
            # Compter combien de fichiers ont une entrée audio dans le store local
            ds = self._get_data_store()
            already = 0
            if ds:
                for p in all_files:
                    if ds.get_audio_cache(p) is not None:
                        already += 1
            self.status_bar.set_info(
                f"Tous les fichiers affichés sont déjà analysés ({already} en cache) — "
                "cochez des cases pour forcer une ré-analyse"
            )
            return

        total = len(files_to_analyze)
        progress = QProgressDialog("Analyse audio en cours…", "Annuler", 0, total, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setWindowTitle("Analyse du son — EBU R128")
        progress.setMinimumDuration(0)
        progress.setValue(0)

        for i, video_path in enumerate(files_to_analyze):
            if progress.wasCanceled():
                break
            progress.setLabelText(
                f"{'Ré-analyse' if force_reanalyze else 'Analyse'} {i + 1}/{total}\n"
                f"{os.path.basename(video_path)}"
            )
            QApplication.processEvents()
            data = self._run_ffmpeg_loudnorm(video_path, subprocess)
            self._set_audio_cache(video_path, data)
            progress.setValue(i + 1)

        progress.close()

        # Conserver la sélection : ne pas déselectionner les lignes
        # Mettre à jour l'affichage des niveaux audio en mode détails sans reconstruire
        if self.view_mode == "details":
            for row in self.row_widgets:
                row._refresh_audio_display()
        # En mode vignettes, l'audio n'est pas affiché, donc rien à rafraîchir

        analyzed = sum(1 for v in self._audio_cache.values() if isinstance(v, dict))
        errors   = sum(1 for v in self._audio_cache.values() if v == "error")
        msg = f"Analyse terminée : {analyzed} fichier(s) analysé(s) au total"
        if errors:
            msg += f", {errors} erreur(s)"
        self.status_bar.set_success(msg)

    def _run_ffmpeg_loudnorm(self, video_path, subprocess_module):
        import json as _json, re as _re
        try:
            result = subprocess_module.run(
                [
                    'ffmpeg', '-hide_banner', '-nostats',
                    '-drc_scale', '0',  # <-- AJOUT : Désactive le Dynamic Range Compression
                    '-i', video_path,
                    '-af', 'aformat=channel_layouts=stereo,loudnorm=I=-23:TP=-1:LRA=11:print_format=json', # <-- AJOUT : Downmix avant loudnorm
                    '-vn', '-f', 'null', '-'
                ],
                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60
            )
            stderr = result.stderr
            m = _re.search(r'\{[^{}]*"input_i"[^{}]*\}', stderr, _re.DOTALL)
            if not m:
                return "error"

            data = _json.loads(m.group(0))
            lufs = float(data.get("input_i", "nan"))
            tp   = float(data.get("input_tp", "nan"))

            import math
            if math.isnan(lufs) or math.isnan(tp):
                return "error"

            return {"lufs": lufs, "true_peak": tp}

        except Exception:
            return "error"

    def normalize_audio(self):
        """Normalise l'audio des fichiers sélectionnés selon la cible choisie dans le combo."""
        import subprocess

        # -- 0. Vérifier ffmpeg --------------------------------------------
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self.status_bar.set_error("ffmpeg introuvable — vérifiez qu'il est installé et dans le PATH")
            return

        # -- 0b. Libérer le media player (évite WinError 5 sur os.replace) -
        self.vlc_player.stop()
        QApplication.processEvents()

        # -- 0c. Lire la cible sélectionnée -------------------------------
        data = self.norm_target_combo.currentData()
        if data is None:
            self.status_bar.set_error("Preset de normalisation invalide")
            return
        TARGET_LUFS, TARGET_TP, USE_PCM = data
        preset_label = self.norm_target_combo.currentText()

        # -- 1. Déterminer les fichiers concernés --------------------------
        checked_paths = {row.video_path for row in self.row_widgets if row.is_checked()}
        all_files = list(self._get_sorted_video_files())
        files_to_process = [p for p in all_files if p in checked_paths] if checked_paths else all_files

        if not files_to_process:
            self.status_bar.set_warning("Aucun fichier à normaliser")
            return

        # -- 2. Bloquer si des fichiers ne sont pas encore analysés --------
        not_analyzed = [p for p in files_to_process
                if self._get_audio_cache(p) is None or not isinstance(self._get_audio_cache(p), dict)]
        if not_analyzed:
            names = "\n  • ".join(os.path.basename(p) for p in not_analyzed[:8])
            suffix = f"\n  … et {len(not_analyzed) - 8} autre(s)" if len(not_analyzed) > 8 else ""
            QMessageBox.warning(
                self, "Analyse requise",
                f"Les fichiers suivants n'ont pas encore été analysés :\n\n"
                f"  • {names}{suffix}\n\n"
                f"Veuillez d'abord cliquer sur « 🔍 Analyser le son »."
            )
            return

        # -- 2b. Bloquer les fichiers déjà normalisés (un seul niveau autorisé) --
        preset_name = preset_label.strip().split("  ")[0].lstrip("📢🔊🔥 ")
        # Extraire le nom propre du preset (ex. "Standard", "Dynamique", "Percutant")
        preset_clean = preset_label.strip().split()[0]  # "Standard", "Dynamique", "Percutant"
        for emoji in ["📢", "🔊", "🔥"]:
            preset_clean = preset_clean.replace(emoji, "")
        preset_clean = preset_clean.strip().split()[0]  # premier mot = nom du preset

        already_normalized_conflict = []
        for p in files_to_process:
            info = self._get_norm_info(p)
            if info and info.get("preset") != preset_clean:
                already_normalized_conflict.append((p, info.get("preset", "?")))

        if already_normalized_conflict:
            lines = "\n".join(
                f"  • {os.path.basename(p)}  (actuellement : {pr})"
                for p, pr in already_normalized_conflict[:8]
            )
            suffix = (f"\n  … et {len(already_normalized_conflict) - 8} autre(s)"
                      if len(already_normalized_conflict) > 8 else "")
            QMessageBox.warning(
                self, "Normalisation impossible",
                f"Les fichiers suivants sont déjà normalisés avec un preset différent :\n\n"
                f"{lines}{suffix}\n\n"
                f"Pour changer de preset, utilisez d'abord « ? Annuler normalisation »\n"
                f"afin de restaurer les fichiers originaux, puis renormalisez."
            )
            return

        # Exclure aussi les fichiers déjà normalisés avec le MÊME preset (cohérent avec already_compliant)
        files_to_process = [p for p in files_to_process
                            if not (self._get_norm_info(p) and
                                    self._get_norm_info(p).get("preset") == preset_clean)]

        if not files_to_process:
            self.status_bar.set_info(
                f"Tous les fichiers sélectionnés sont déjà normalisés en « {preset_clean} »"
            )
            return


        # Un fichier est "déjà conforme" seulement si son LUFS est très proche
        # de la cible PAR LE BAS (trop fort n'est jamais ignoré).
        LUFS_TOL = 0.5   # tolérance basse : on accepte jusqu'à TARGET_LUFS + 0.5
        TP_TOL   = 0.5

        def already_compliant(path):
            data = self._get_audio_cache(path)
            if not isinstance(data, dict):
                return False
            lufs = data.get("lufs")
            tp   = data.get("true_peak")
            if lufs is None or tp is None:
                return False
            # Conforme uniquement si le LUFS est dans la fenêtre [TARGET-0.5, TARGET+0.5]
            # ET le True Peak est déjà sous la limite.
            lufs_ok = (TARGET_LUFS - LUFS_TOL) <= lufs <= (TARGET_LUFS + LUFS_TOL)
            tp_ok   = tp <= (TARGET_TP + TP_TOL)
            return lufs_ok and tp_ok

        skipped = [p for p in files_to_process if already_compliant(p)]
        files_to_normalize = [p for p in files_to_process if not already_compliant(p)]

        if not files_to_normalize:
            self.status_bar.set_info(
                f"Tous les fichiers sont déjà conformes à la cible "
                f"({len(skipped)} ignoré{'s' if len(skipped) > 1 else ''})"
            )
            return

        # -- 4. Boîte de confirmation --------------------------------------
        skip_note = f"\n{len(skipped)} fichier(s) déjà conformes seront ignorés." if skipped else ""
        reply = QMessageBox.question(
            self, "Normalisation audio",
            f"Normaliser {len(files_to_normalize)} fichier(s) ?\n\n"
            f"Cible : {TARGET_LUFS:+.0f} LUFS intégré / True Peak {TARGET_TP:+.1f} dBTP\n"
            f"Préréglage : {preset_label.strip()}\n\n"
            f"La piste vidéo sera copiée sans modification.\n"
            f"Un backup sera créé dans .normalized_backup/ pour chaque fichier.{skip_note}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            self.status_bar.set_info("Normalisation annulée")
            return

        # -- 5. Traitement fichier par fichier -----------------------------
        total = len(files_to_normalize)
        progress = QProgressDialog("Normalisation en cours…", "Annuler", 0, total, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setWindowTitle("Normalisation audio — EBU R128")
        progress.setMinimumDuration(0)
        progress.setValue(0)

        success_count = 0
        error_files = []
        # Fichiers normalisés avec succès — pour re-analyse immédiate
        success_paths = []

        for i, video_path in enumerate(files_to_normalize):
            if progress.wasCanceled():
                break
            progress.setLabelText(
                f"Normalisation {i + 1}/{total}\n{os.path.basename(video_path)}"
            )
            QApplication.processEvents()

            # Sauvegarder la valeur pré-normalisation avant de vider le cache
            old_data = self._get_audio_cache(video_path)
            if isinstance(old_data, dict):
                self._pre_norm_cache[video_path] = old_data.copy()

            err = self._normalize_one_file(video_path, TARGET_LUFS, TARGET_TP, subprocess, use_pcm=USE_PCM)
            if err is None:
                success_count += 1
                 # (on ne pop plus du cache global, mais on peut le laisser ou le nettoyer)
                self._set_norm_info(video_path, preset_clean, old_data if isinstance(old_data, dict) else None)
                success_paths.append(video_path)
            else:
                error_files.append((os.path.basename(video_path), err))

            progress.setValue(i + 1)

        progress.close()

        # -- Re-analyser immédiatement les fichiers normalisés -------------
        if success_paths:
            re_total = len(success_paths)
            re_progress = QProgressDialog(
                "Re-analyse audio post-normalisation…", None, 0, re_total, self
            )
            re_progress.setWindowModality(Qt.WindowModality.WindowModal)
            re_progress.setWindowTitle("Mise à jour des niveaux")
            re_progress.setMinimumDuration(0)
            re_progress.setValue(0)
            for j, video_path in enumerate(success_paths):
                re_progress.setLabelText(
                    f"Re-analyse {j + 1}/{re_total}\n{os.path.basename(video_path)}"
                )
                QApplication.processEvents()
                data = self._run_ffmpeg_loudnorm(video_path, subprocess)
                self._set_audio_cache(video_path, data)
                re_progress.setValue(j + 1)
            re_progress.close()

        # Décocher tout
        for row in self.row_widgets:
            if row.is_checked():
                row.set_checked(False)

        # Rafraîchir l'affichage
        if self.view_mode == "details":
            self.display_videos()
        elif self.view_mode == "thumbnails":
            for container in self.thumbnail_containers:
                container._refresh_norm_badge()

        if error_files:
            detail = "\n".join(f"  • {n} : {e}" for n, e in error_files[:6])
            QMessageBox.warning(
                self, "Normalisation — erreurs",
                f"{success_count} fichier(s) normalisé(s) avec succès.\n\n"
                f"Erreurs ({len(error_files)}) :\n{detail}"
            )
        else:
            skip_info = f" ({len(skipped)} déjà conformes ignorés)" if skipped else ""
            self.status_bar.set_success(
                f"Normalisation terminée : {success_count} fichier(s) traité(s){skip_info}"
            )

    def _normalize_one_file(self, video_path, target_lufs, target_tp, subprocess_module, use_pcm=True):
        """
        Normalise un fichier vidéo en deux passes ffmpeg (loudnorm).
        use_pcm=True  -> audio PCM 16 bits (qualité max, sans perte)
        use_pcm=False -> ré-encode dans le codec d'origine (ou AAC si non supporté)
        """
        import json as _json, re as _re, tempfile

        video_dir  = os.path.dirname(video_path)
        video_name = os.path.basename(video_path)
        backup_dir = os.path.join(video_dir, ".normalized_backup")

        try:
            os.makedirs(backup_dir, exist_ok=True)
        except Exception as e:
            return f"Impossible de créer le dossier backup : {e}"

        backup_path = os.path.join(backup_dir, video_name)

        if not os.path.exists(backup_path):
            try:
                import shutil as _shutil
                _shutil.copy2(video_path, backup_path)
            except Exception as e:
                return f"Erreur lors de la création du backup : {e}"

        # Passe 1 : mesure
        cache_data = self._get_audio_cache(video_path)
        if isinstance(cache_data, dict):
            measured_i      = cache_data.get("lufs", -99.0)
            measured_tp     = cache_data.get("true_peak", -99.0)
            measured_lra    = 11.0
            measured_thresh = -99.0
            measured_offset = 0.0
            pass1_needed = False
        else:
            pass1_needed = True

        if pass1_needed:
            try:
                r1 = subprocess_module.run(
                    [
                        'ffmpeg', '-hide_banner', '-nostats',
                        '-drc_scale', '0',
                        '-i', video_path,
                        '-af', f'loudnorm=I={target_lufs}:TP={target_tp}:LRA=11:print_format=json',
                        '-vn', '-f', 'null', '-'
                    ],
                    capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120
                )
                m = _re.search(r'\{[^{}]*"input_i"[^{}]*\}', r1.stderr, _re.DOTALL)
                if not m:
                    return "Passe 1 : impossible de lire les mesures loudnorm"
                meas = _json.loads(m.group(0))
                measured_i      = meas.get("input_i",      "-99.0")
                measured_tp     = meas.get("input_tp",     "-99.0")
                measured_lra    = meas.get("input_lra",    "11.0")
                measured_thresh = meas.get("input_thresh", "-99.0")
                measured_offset = meas.get("target_offset","0.0")
            except Exception as e:
                return f"Passe 1 : {e}"

        # Lecture du sample rate et du codec d'origine
        source_sample_rate = None
        source_audio_codec = None
        try:
            r_probe = subprocess_module.run(
                [
                    'ffprobe', '-v', 'error',
                    '-select_streams', 'a:0',
                    '-show_entries', 'stream=sample_rate,codec_name',
                    '-of', 'default=noprint_wrappers=1',
                    video_path
                ],
                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30
            )
            for line in r_probe.stdout.strip().splitlines():
                if '=' in line:
                    key, val = line.split('=', 1)
                    if key == 'sample_rate' and val.strip().isdigit():
                        source_sample_rate = int(val.strip())
                    elif key == 'codec_name' and val.strip():
                        source_audio_codec = val.strip()
        except Exception:
            pass

        # Fichier temporaire
        suffix = os.path.splitext(video_name)[1]
        try:
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix, dir=video_dir)
            os.close(tmp_fd)
        except Exception as e:
            return f"Impossible de créer le fichier temporaire : {e}"

        af_filter = (
            f"aformat=channel_layouts=stereo,"  # <-- AJOUT : Downmix stéréo initial
            f"loudnorm=I={target_lufs}:TP={target_tp}:LRA=11"
            f":measured_I={measured_i}"
            f":measured_TP={measured_tp}"
            f":measured_LRA={measured_lra}"
            f":measured_thresh={measured_thresh}"
            f":offset={measured_offset}"
            f":linear=true:print_format=none"
        )

        # Construction de la commande ffmpeg
        cmd = [
            'ffmpeg',
            '-drc_scale', '0',  # <-- AJOUT : Désactive le DRC au décodage
            '-fflags', '+genpts',
            '-hide_banner', '-nostats', '-y',
            '-i', video_path,
            '-c:v', 'copy',
            '-af', af_filter,
        ]
        if use_pcm:
            cmd.extend(['-c:a', 'pcm_s16le'])
        else:
            # Ré-encoder dans le codec d'origine si supporté, sinon AAC
            if source_audio_codec in ['aac', 'mp3', 'opus', 'vorbis', 'flac']:
                cmd.extend(['-c:a', source_audio_codec])
            else:
                cmd.extend(['-c:a', 'aac', '-b:a', '192k'])
        cmd.extend(['-async', '1', '-max_muxing_queue_size', '1024'])
        if source_sample_rate:
            cmd.extend(['-ar', str(source_sample_rate)])
        cmd.append(tmp_path)

        try:
            r2 = subprocess_module.run(
                cmd,
                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=600
            )
            if r2.returncode != 0:
                os.remove(tmp_path)
                return f"Passe 2 ffmpeg : code {r2.returncode}"
        except Exception as e:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
            return f"Passe 2 : {e}"

        # Remplacement atomique
        try:
            os.replace(tmp_path, video_path)
        except Exception as e:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
            return f"Remplacement du fichier : {e}"

        return None

    def revert_normalization(self):
        """Restaure les fichiers depuis .normalized_backup/."""
        # Libérer le media player pour éviter les verrous fichiers (WinError 5)
        self.vlc_player.stop()
        QApplication.processEvents()

        checked_paths = {row.video_path for row in self.row_widgets if row.is_checked()}
        all_files = list(self._get_sorted_video_files())
        files_to_check = [p for p in all_files if p in checked_paths] if checked_paths else all_files

        if not files_to_check:
            self.status_bar.set_warning("Aucun fichier à restaurer")
            return

        # Identifier les fichiers qui ont un backup
        restorable = []
        for video_path in files_to_check:
            video_dir  = os.path.dirname(video_path)
            video_name = os.path.basename(video_path)
            backup_path = os.path.join(video_dir, ".normalized_backup", video_name)
            if os.path.exists(backup_path):
                restorable.append((video_path, backup_path))

        if not restorable:
            self.status_bar.set_warning(
                "Aucun backup trouvé — les fichiers n'ont peut-être pas encore été normalisés"
            )
            return

        reply = QMessageBox.question(
            self, "Annuler la normalisation",
            f"Restaurer {len(restorable)} fichier(s) depuis les backups ?\n\n"
            f"Le fichier normalisé sera remplacé par l'original.\n"
            f"Cette action est irréversible (le fichier normalisé sera perdu).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            self.status_bar.set_info("Restauration annulée")
            return

        import shutil as _shutil
        success_count = 0
        error_files = []
        restored_paths = []

        for video_path, backup_path in restorable:
            try:
                _shutil.copy2(backup_path, video_path)
                os.remove(backup_path)
                # Vider le cache audio ET le pré-cache pour forcer une ré-analyse
                self._audio_cache.pop(video_path, None)
                self._pre_norm_cache.pop(video_path, None)
                self._clear_norm_info(video_path)
                success_count += 1
                restored_paths.append(video_path)
                # Nettoyer le dossier backup s'il est vide
                backup_dir = os.path.dirname(backup_path)
                try:
                    if not os.listdir(backup_dir):
                        os.rmdir(backup_dir)
                except Exception:
                    pass
            except Exception as e:
                error_files.append((os.path.basename(video_path), str(e)))

        # Décocher tout
        for row in self.row_widgets:
            if row.is_checked():
                row.set_checked(False)

        # -- Re-analyser immédiatement les fichiers restaurés -------------
        if restored_paths:
            import subprocess as _subprocess
            re_total = len(restored_paths)
            re_progress = QProgressDialog(
                "Re-analyse audio des fichiers restaurés…", None, 0, re_total, self
            )
            re_progress.setWindowModality(Qt.WindowModality.WindowModal)
            re_progress.setWindowTitle("Analyse audio post-restauration")
            re_progress.setMinimumDuration(0)
            re_progress.setValue(0)
            for j, video_path in enumerate(restored_paths):
                re_progress.setLabelText(
                    f"Re-analyse {j + 1}/{re_total}\n{os.path.basename(video_path)}"
                )
                QApplication.processEvents()
                data = self._run_ffmpeg_loudnorm(video_path, _subprocess)
                self._set_audio_cache(video_path, data)
                re_progress.setValue(j + 1)
            re_progress.close()

        # Rafraîchir l'affichage dans les deux modes
        if self.view_mode == "details":
            self.display_videos()
        elif self.view_mode == "thumbnails":
            for container in self.thumbnail_containers:
                container._refresh_norm_badge()

        if error_files:
            detail = "\n".join(f"  • {n} : {e}" for n, e in error_files[:6])
            QMessageBox.warning(
                self, "Restauration — erreurs",
                f"{success_count} fichier(s) restauré(s).\n\nErreurs :\n{detail}"
            )
        else:
            self.status_bar.set_success(
                f"Restauration terminée : {success_count} fichier(s) remis à l'original"
            )

    def purge_backups(self):
        """Envoie les backups des fichiers affichés (ou sélectionnés) dans la corbeille Windows."""
        checked_paths = {row.video_path for row in self.row_widgets if row.is_checked()}
        all_files = list(self._get_sorted_video_files())
        files_to_check = [p for p in all_files if p in checked_paths] if checked_paths else all_files

        if not files_to_check:
            self.status_bar.set_warning("Aucun fichier à traiter")
            return

        # Identifier les fichiers qui ont effectivement un backup
        purgeable = []
        for video_path in files_to_check:
            video_dir  = os.path.dirname(video_path)
            video_name = os.path.basename(video_path)
            backup_path = os.path.join(video_dir, ".normalized_backup", video_name)
            if os.path.exists(backup_path):
                purgeable.append((video_path, backup_path))

        if not purgeable:
            self.status_bar.set_warning(
                "Aucun backup trouvé pour les fichiers affichés"
            )
            return

        scope = "sélectionnés" if checked_paths else "affichés"
        
        # --- MODIFICATION 1 : Mise à jour du texte d'avertissement ---
        reply = QMessageBox.warning(
            self, "🗑️ Purge des backups vers la corbeille",
            f"Vous allez envoyer {len(purgeable)} backup(s) dans la corbeille Windows "
            f"parmi les fichiers {scope}.\n\n"
            f"⚠️ CONSÉQUENCES :\n"
            f"  • Dans l'application, la réversion vers l'original deviendra impossible.\n"
            f"  • Vous pourrez toujours les récupérer manuellement depuis la corbeille en cas d'erreur.\n\n"
            f"Confirmer la suppression ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            self.status_bar.set_info("Purge annulée")
            return

        success_count = 0
        error_files = []

        # --- MODIFICATION 2 : Préparation de l'API Corbeille de Windows ---
        import ctypes
        from ctypes import wintypes

        SHFileOperationW = ctypes.windll.shell32.SHFileOperationW

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd",                  wintypes.HWND),
                ("wFunc",                 wintypes.UINT),
                ("pFrom",                 wintypes.LPCWSTR),
                ("pTo",                   wintypes.LPCWSTR),
                ("fFlags",                ctypes.c_uint16),
                ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings",         ctypes.c_void_p),
                ("lpszProgressTitle",     wintypes.LPCWSTR),
            ]

        FO_DELETE      = 0x0003
        FOF_ALLOWUNDO  = 0x0040       # Autorise l'envoi à la corbeille
        FOF_NOCONFIRMATION = 0x0010   # Pas de popup Windows
        FOF_SILENT     = 0x0004       # Silencieux

        # --- MODIFICATION 3 : Remplacement de os.remove dans la boucle ---
        for video_path, backup_path in purgeable:
            try:
                # Le chemin doit se terminer par un double \0 pour l'API Windows
                path_buf = backup_path + "\0"

                op = SHFILEOPSTRUCTW()
                op.hwnd   = 0
                op.wFunc  = FO_DELETE
                op.pFrom  = path_buf
                op.pTo    = None
                op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT

                ret = SHFileOperationW(ctypes.byref(op))
                if ret != 0:
                    raise RuntimeError(f"Erreur Windows (code {ret})")

                success_count += 1
                
                # Nettoyer le dossier backup s'il est vide
                backup_dir = os.path.dirname(backup_path)
                try:
                    if not os.listdir(backup_dir):
                        os.rmdir(backup_dir)
                except Exception:
                    pass
            except Exception as e:
                error_files.append((os.path.basename(video_path), str(e)))

        # Décocher tout
        for row in self.row_widgets:
            if row.is_checked():
                row.set_checked(False)

        if error_files:
            detail = "\n".join(f"  • {n} : {e}" for n, e in error_files[:6])
            QMessageBox.warning(
                self, "Purge — erreurs",
                f"{success_count} backup(s) envoyé(s) à la corbeille.\n\nErreurs :\n{detail}"
            )
        else:
            self.status_bar.set_success(
                f"Purge terminée : {success_count} backup(s) envoyé(s) à la corbeille"
            )

    # ----------------------------------------------------------------------
    # v7.0 — Tags
    # ----------------------------------------------------------------------

    def _get_data_store(self):
        """Retourne le FolderDataStore unique pour la racine du dossier source."""
        if not self.current_folder or not os.path.isdir(self.current_folder):
            return None
        if self._data_store is None or getattr(self._data_store, 'root_path', '') != self.current_folder:
            self._data_store = FolderDataStore(self.current_folder)
            self._data_store.import_from_global_config(
                self._audio_cache, self._norm_history, self.copy_counts
            )
        return self._data_store
    
    def backup_data_store(self):
        """Sauvegarde horodatée du fichier _videoviewer_data.json du dossier source courant.
        Conserve les 8 sauvegardes les plus récentes dans le dossier !JSON_Backups."""
        if not self.current_folder or not os.path.isdir(self.current_folder):
            return

        ds = self._get_data_store()
        if ds is None:
            return

        json_path = Path(ds._json_path())
        if not json_path.exists():
            return

        backup_dir = json_path.parent / "!JSON_Backups"
        try:
            backup_dir.mkdir(exist_ok=True)
        except OSError:
            return  # silencieux

        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{json_path.stem}_{timestamp}{json_path.suffix}"
        backup_path = backup_dir / backup_name

        try:
            shutil.copy2(json_path, backup_path)
        except (OSError, shutil.Error):
            return

        # Rotation : ne garder que les 8 plus récents
        import glob
        pattern = str(backup_dir / f"{json_path.stem}_*{json_path.suffix}")
        try:
            backups = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
            for old in backups[8:]:
                try:
                    os.remove(old)
                except OSError:
                    pass
        except Exception:
            pass
    
    # --- Helpers pour accéder aux métadonnées via le store local ---
    def _get_audio_cache(self, video_path):
        ds = self._get_data_store()
        if ds:
            return ds.get_audio_cache(video_path)
        return None

    def _set_audio_cache(self, video_path, data):
        ds = self._get_data_store()
        if ds:
            ds.set_audio_cache(video_path, data)

    def _get_norm_info(self, video_path):
        ds = self._get_data_store()
        if ds:
            return ds.get_norm_history(video_path)
        return None

    def _set_norm_info(self, video_path, preset_name, pre_norm_data=None):
        from datetime import date
        ds = self._get_data_store()
        if not ds:
            return
        info = {
            "preset": preset_name,
            "date": date.today().strftime("%d/%m/%Y"),
        }
        if pre_norm_data:
            info["pre_lufs"] = pre_norm_data.get("lufs")
            info["pre_tp"] = pre_norm_data.get("true_peak")
        ds.set_norm_history(video_path, info)

    def _clear_norm_info(self, video_path):
        ds = self._get_data_store()
        if ds:
            ds.clear_norm_history(video_path)

    def _refresh_tag_panel(self):
        try:
            ds = self._get_data_store()
            if ds is not None:
                ds._load()   # recharge le fichier JSON
            if hasattr(self, 'tag_panel'):
                self.tag_panel.refresh(ds, [])
                # forcer un rafraîchissement immédiat
                self.tag_panel.update()
                self.tag_panel.repaint()
                self.tag_panel._tag_list.update()
                self.tag_panel._tag_list.repaint()
        except Exception as e:
            import traceback
            QMessageBox.critical(self, "Erreur rafraîchissement panneau tags",
                f"{str(e)}\n\n{traceback.format_exc()}")

    def _on_tag_filter_changed(self, filter_spec):
        """Appelé quand l'utilisateur clique sur un filtre ou tag dans le panneau."""
        self._tag_filter = filter_spec
        self._apply_tag_filter()

    def _load_full_catalog_in_background(self):
        """Charge silencieusement la liste complète des vidéos de la racine."""
        if not self.current_folder:
            return
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm', '.m4v']
        found = []
        try:
            for root, dirs, files in os.walk(self.current_folder):
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for file in files:
                    if any(file.lower().endswith(ext) for ext in video_extensions):
                        found.append(os.path.join(root, file))
            found.sort()
            self.full_catalog = found
            print(f"[DEBUG] full_catalog chargé en arrière-plan : {len(self.full_catalog)} fichiers")
        except Exception as e:
            print(f"[DEBUG] Erreur chargement full_catalog : {e}")

    def _apply_tag_filter(self):
        ds = self._get_data_store()
        if not ds:
            self.video_files = []
            self.display_videos()
            return

        # Extraire les filtres
        system_filter = None
        tag_filters = []
        valence_filter = None

        for ftype, fval in self._tag_filter:
            if ftype == "system":
                system_filter = fval
            elif ftype == "tag":
                tag_filters.append(fval)
            elif ftype == "valence":
                valence_filter = fval

        # Si absolument aucun filtre, afficher tout
        if system_filter is None and not tag_filters and valence_filter is None:
            if getattr(self, 'full_catalog', None):
                self.all_video_files = list(self.full_catalog)
            self.video_files = list(self.all_video_files)
            self.lbl_search_count.setText("")
            self.display_videos()
            return

        # --- FIX V8.2 BUG TAGS/FILMS ---
        # Si on filtre par tags et que le catalogue complet existe, on l'utilise comme base de travail.
        # Cela évite d'être bloqué sur la sélection restreinte du dernier "Film" cliqué.
        if getattr(self, 'full_catalog', None):
            base_files = list(self.full_catalog)
        else:
            base_files = list(self.all_video_files)

        filtered = list(base_files)
        # -------------------------------

        # 1. Filtre système
        if system_filter is not None:
            if system_filter == "all":
                pass
            elif system_filter == "untagged":
                filtered = [p for p in filtered if not ds.get_tags(p)]
            elif system_filter == "multitag":
                filtered = [p for p in filtered if len(ds.get_tags(p)) >= 2]
            elif system_filter in ("none", "partial", "backed"):
                if system_filter == "none":
                    pass
                elif system_filter == "backed":
                    filtered = []
                else:
                    pass

        # 2. Filtre par tags (ET logique)
        if tag_filters:
            filtered = [p for p in filtered
                        if all(tag in ds.get_tags(p) for tag in tag_filters)]

        # 3. Filtre par valence
        if valence_filter is not None:
            if valence_filter == "all":
                filtered = [p for p in filtered
                            if any(ds.get_tag_valence(t) in ("positif", "negatif", "neutre")
                                for t in ds.get_tags(p))]
            elif valence_filter in ("positif", "negatif", "neutre"):
                filtered = [p for p in filtered
                            if any(ds.get_tag_valence(t) == valence_filter
                                for t in ds.get_tags(p))]

        self.video_files = filtered
        count = len(self.video_files)
        self.status_bar.set_success(f"{count} vidéo{'s' if count > 1 else ''} trouvée{'s' if count > 1 else ''}")
        
        # Mettre à jour all_video_files pour refléter la base de recherche cohérente
        self.all_video_files = list(base_files)
        
        total = len(self.all_video_files)
        found = len(filtered)
        color = "#28a745" if found > 0 else "#dc3545"
        self.lbl_search_count.setText(
            f'<span style="color:{color};">{found}</span>'
            f'<span style="color:#666;"> / {total}</span>'
        )
        self.display_videos()
        self._refresh_tag_panel()

    def open_tag_dialog(self):
        """Ouvre un dialogue pour tagger les vignettes sélectionnées.
        Ne nécessite pas le Mode Gestion."""
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                                     QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem)

        selected = self._get_selected_video_paths()
        if not selected:
            self.status_bar.set_warning("Sélectionnez d'abord une ou plusieurs vignettes")
            return

        if not self.current_folder:
            self.status_bar.set_warning("Aucun dossier source chargé")
            return

        # S'assurer que le store est initialisé sur le dossier racine
        ds = self._get_data_store()
        if ds is None:
            self.status_bar.set_warning("Impossible d'accéder aux données du dossier")
            return

        # Calculer les tags communs et partiels
        all_file_tags  = [set(ds.get_tags(p)) for p in selected]
        common_tags    = set.intersection(*all_file_tags) if all_file_tags else set()
        all_tags_union = set.union(*all_file_tags)        if all_file_tags else set()
        existing_tags  = sorted(ds.all_tags().keys())

        dlg = QDialog(self)
        dlg.setWindowTitle(f"🏷 Tags — {len(selected)} fichier(s)")
        dlg.setMinimumWidth(360)
        dlg.setStyleSheet("background-color: #2b2b2b; color: white;")
        vl = QVBoxLayout(dlg)

        info = QLabel(f"Fichier{'s' if len(selected)>1 else ''} sélectionné{'s' if len(selected)>1 else ''} : {len(selected)}")
        info.setStyleSheet("color: #aaa; font-size: 11px;")
        vl.addWidget(info)

        tag_list = QListWidget()
        tag_list.setStyleSheet("""
            QListWidget { background: #1e1e1e; border: 1px solid #444; }
            QListWidget::item { padding: 4px 8px; }
        """)
        tag_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        all_known = sorted(set(existing_tags) | all_tags_union)
        tag_checks = {}
        for tag in all_known:
            item = QListWidgetItem(f"  {tag}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if tag in common_tags:
                item.setCheckState(Qt.CheckState.Checked)
            elif tag in all_tags_union:
                item.setCheckState(Qt.CheckState.PartiallyChecked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            tag_checks[tag] = item
            tag_list.addItem(item)
        vl.addWidget(tag_list)

        # Champ nouveau tag
        hl_new = QHBoxLayout()
        new_tag_edit = QLineEdit()
        new_tag_edit.setPlaceholderText("Nouveau tag…")
        new_tag_edit.setStyleSheet("background: #1e1e1e; color: white; border: 1px solid #555; padding: 4px;")
        hl_new.addWidget(new_tag_edit)
        btn_add_tag = QPushButton("+")
        btn_add_tag.setFixedWidth(28)
        btn_add_tag.setStyleSheet("QPushButton { background: #1a5a1a; color: white; border: none; padding: 4px; }")

        def _add_new_tag():
            t = new_tag_edit.text().strip().lower()
            if t and t not in tag_checks:
                item = QListWidgetItem(f"  {t}")
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                tag_checks[t] = item
                tag_list.addItem(item)
                new_tag_edit.clear()

        btn_add_tag.clicked.connect(_add_new_tag)
        new_tag_edit.returnPressed.connect(_add_new_tag)
        hl_new.addWidget(btn_add_tag)
        vl.addLayout(hl_new)

        hl_btns = QHBoxLayout()
        btn_ok     = QPushButton("✅ Appliquer")
        btn_cancel = QPushButton("Annuler")
        btn_ok.setStyleSheet("QPushButton { background: #0078d4; padding: 7px; } QPushButton:hover { background: #1084d8; }")
        btn_cancel.setStyleSheet("QPushButton { background: #444; padding: 7px; }")
        hl_btns.addWidget(btn_ok)
        hl_btns.addWidget(btn_cancel)
        vl.addLayout(hl_btns)
        btn_cancel.clicked.connect(dlg.reject)

        def _apply():
            for tag, item in tag_checks.items():
                state = item.checkState()
                for path in selected:
                    if state == Qt.CheckState.Checked:
                        ds.add_tag(path, tag)
                    elif state == Qt.CheckState.Unchecked:
                        ds.remove_tag(path, tag)
                    # PartiallyChecked = on ne touche pas
            # Forcer la sauvegarde du JSON
            ds.save()
            self._refresh_tag_panel()
            dlg.accept()
            self.status_bar.set_success(f"🏷 Tags mis à jour pour {len(selected)} fichier(s)")

        btn_ok.clicked.connect(_apply)
        dlg.exec()

    def create_global_tag(self, tag):
        """Crée un tag vide (sans l'attribuer à un fichier) — juste pour le faire apparaître."""
        # Les tags n'existent que s'ils sont attribués à au moins un fichier.
        # On ouvre directement le dialogue de tagging.
        self.open_tag_dialog()

    def rename_file(self, old_path):
        from PyQt6.QtWidgets import QInputDialog
        old_name = os.path.basename(old_path)
        new_name, ok = QInputDialog.getText(
            self, "Renommer le fichier",
            f"Nouveau nom pour :\n{old_name}",
            text=old_name
        )
        if not ok or not new_name.strip() or new_name == old_name:
            return
        new_name = new_name.strip()
        if not new_name.lower().endswith(tuple(FolderTreeWidget.VIDEO_EXTENSIONS)):
            ext = os.path.splitext(old_name)[1]
            new_name += ext
        dir_name = os.path.dirname(old_path)
        new_path = os.path.join(dir_name, new_name)
        if os.path.exists(new_path):
            self.status_bar.set_error(f"Un fichier nommé '{new_name}' existe déjà.")
            return
        try:
            # ✅ Libérer VLC avant tout accès fichier
            self.vlc_player.stop()
            self.vlc_player.set_media(None)  # détache complètement le media
            QApplication.processEvents()     # laisse VLC fermer ses handles

            os.rename(old_path, new_path)
            ds = self._get_data_store()
            if ds:
                ds.update_path(old_path, new_path)
            if old_path in self.all_video_files:
                idx = self.all_video_files.index(old_path)
                self.all_video_files[idx] = new_path
            if old_path in self.video_files:
                idx = self.video_files.index(old_path)
                self.video_files[idx] = new_path
            self.display_videos()
            self.status_bar.set_success(f"Fichier renommé en '{new_name}'")
        except Exception as e:
            self.status_bar.set_error(f"Erreur lors du renommage : {e}")

    def trash_file(self, video_path):
        filename = os.path.basename(video_path)
        reply = QMessageBox.question(
            self, "Confirmer la suppression",
            f"Envoyer « {filename} » dans la corbeille ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            self.status_bar.set_info("Suppression annulée")
            return

        try:
            self.vlc_player.stop()
            self.vlc_player.set_media(None)
            QApplication.processEvents()

            # Utilise l'API Windows SHFileOperation pour envoyer à la corbeille
            import ctypes
            from ctypes import wintypes

            SHFileOperationW = ctypes.windll.shell32.SHFileOperationW

            class SHFILEOPSTRUCTW(ctypes.Structure):
                _fields_ = [
                    ("hwnd",                  wintypes.HWND),
                    ("wFunc",                 wintypes.UINT),
                    ("pFrom",                 wintypes.LPCWSTR),
                    ("pTo",                   wintypes.LPCWSTR),
                    ("fFlags",                ctypes.c_uint16),
                    ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings",         ctypes.c_void_p),
                    ("lpszProgressTitle",     wintypes.LPCWSTR),
                ]

            FO_DELETE      = 0x0003
            FOF_ALLOWUNDO  = 0x0040   # envoie à la corbeille
            FOF_NOCONFIRMATION = 0x0010
            FOF_SILENT     = 0x0004

            # pFrom doit se terminer par double \0
            path_buf = video_path + "\0"

            op = SHFILEOPSTRUCTW()
            op.hwnd   = 0
            op.wFunc  = FO_DELETE
            op.pFrom  = path_buf
            op.pTo    = None
            op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT

            ret = SHFileOperationW(ctypes.byref(op))
            if ret != 0:
                raise RuntimeError(f"SHFileOperation a retourné le code {ret}")

            # Retirer le fichier des listes internes
            for lst in (self.all_video_files, self.video_files):
                if video_path in lst:
                    lst.remove(video_path)
            if self.full_catalog and video_path in self.full_catalog:
                self.full_catalog.remove(video_path)

            if self.current_selected_video == video_path:
                self.current_selected_video = None
                # self.update_copy_button_state()

            self.display_videos()
            self.status_bar.set_success(f"« {filename} » envoyé dans la corbeille")

        except Exception as e:
            import traceback
            QMessageBox.critical(self, "Erreur suppression", f"{e}\n\n{traceback.format_exc()}")
            self.status_bar.set_error(f"Erreur lors de la suppression : {e}")
        
    def rename_tag(self, old_tag, new_tag):
        ds = self._get_data_store()
        if not ds:
            return
        for name in list(ds._data.keys()):
            tags = ds._data[name].get("tags", [])
            if old_tag in tags:
                tags = [new_tag if t == old_tag else t for t in tags]
                ds._data[name]["tags"] = sorted(set(tags))
        ds.save()
        self._refresh_tag_panel()
        self.status_bar.set_success(f"Tag « {old_tag} » renommé en « {new_tag} »")

    def rename_tag(self, old_tag, new_tag):
        print(f"[DEBUG] rename_tag appelé : old='{old_tag}', new='{new_tag}'")
        ds = self._get_data_store()
        if not ds:
            print("[DEBUG] rename_tag: ds est None")
            return
        print(f"[DEBUG] rename_tag: ds.root_path={ds.root_path}")

        renamed_count = 0
        for name in list(ds._data.keys()):
            if name in ("_global_tags", "_tag_valences"):
                continue
            tags = ds._data[name].get("tags", [])
            if old_tag in tags:
                ds._data[name]["tags"] = [new_tag if t == old_tag else t for t in tags]
                renamed_count += 1
        print(f"[DEBUG] rename_tag: tag renommé dans {renamed_count} fichiers")

        # Mise à jour de _global_tags
        global_entry = ds._data.get("_global_tags", {})
        if "tags" in global_entry:
            tags_list = global_entry["tags"]
            if old_tag in tags_list:
                tags_list.remove(old_tag)
                tags_list.append(new_tag)
                print(f"[DEBUG] rename_tag: _global_tags mis à jour : {tags_list}")

        # Transfert de valence
        old_valence = ds.get_tag_valence(old_tag)
        print(f"[DEBUG] rename_tag: ancienne valence = {old_valence}")
        if old_valence != "neutre":
            ds.set_tag_valence(new_tag, old_valence)
        ds.remove_tag_valence(old_tag)

        ds.save()
        print("[DEBUG] rename_tag: sauvegarde effectuée")
        self._refresh_tag_panel()
        self.status_bar.set_success(f"Tag « {old_tag} » renommé en « {new_tag} »")
        print("[DEBUG] rename_tag: terminé")

    def delete_tag(self, tag):
        print(f"[DEBUG] delete_tag appelé avec tag='{tag}'")
        ds = self._get_data_store()
        if not ds:
            print("[DEBUG] delete_tag: ds est None")
            return
        print(f"[DEBUG] delete_tag: ds.root_path={ds.root_path}")

        # Vérifier si le tag est orphelin (dans _global_tags)
        global_tags_entry = ds._data.get("_global_tags", {})
        global_tags = global_tags_entry.get("tags", [])
        print(f"[DEBUG] delete_tag: _global_tags avant = {global_tags}")

        # Supprimer le tag de tous les fichiers
        removed_from_files = 0
        for name in list(ds._data.keys()):
            if name in ("_global_tags", "_tag_valences"):
                continue
            tags = ds._data[name].get("tags", [])
            if tag in tags:
                ds._data[name]["tags"] = [t for t in tags if t != tag]
                removed_from_files += 1
        print(f"[DEBUG] delete_tag: tag retiré de {removed_from_files} fichiers")

        # Nettoyer la valence associée
        ds.remove_tag_valence(tag)
        print("[DEBUG] delete_tag: valence nettoyée")

        # Supprimer le tag de _global_tags s'il y est
        if tag in global_tags:
            global_tags.remove(tag)
            if not global_tags:
                del ds._data["_global_tags"]["tags"]
            print(f"[DEBUG] delete_tag: _global_tags après = {ds._data.get('_global_tags', {}).get('tags', [])}")

        ds.save()
        print("[DEBUG] delete_tag: sauvegarde effectuée")

        # Rafraîchir le panneau de tags
        if hasattr(self, 'tag_panel'):
            self.tag_panel.refresh_panel_only(ds, self._backup_dests)
            print("[DEBUG] delete_tag: panneau rafraîchi")

        self.status_bar.set_success(f"Tag « {tag} » supprimé de tous les fichiers")
        print("[DEBUG] delete_tag: succès")
    
    def _get_selected_video_paths(self):
        """Retourne la liste des chemins des vignettes/lignes sélectionnées."""
        selected = []
        for container in self.thumbnail_containers:
            if container.thumbnail.is_selected:
                selected.append(container.video_path)
        for row in self.row_widgets:
            if row.is_selected:
                selected.append(row.video_path)
        # Si rien de sélectionné mais une vignette courante
        if not selected and self.current_selected_video:
            selected = [self.current_selected_video]
        return selected

    # def _refresh_save_badges(self):
    #     """Rafraîchit les badges de sauvegarde sur toutes les vignettes visibles."""
    #     ds = self._get_data_store()
    #     dest_labels = [d["label"] for d in self._backup_dests]
    #     for container in self.thumbnail_containers:
    #         if hasattr(container, 'save_badge') and container.save_badge is not None:
    #             status = ds.backup_status(container.video_path, dest_labels) if ds else "none"
    #             container.save_badge.update_status(status)


    def save_settings(self):
        """Sauvegarde manuelle (bouton 💾) — appelle _do_save et confirme"""
        print(f"[DEBUG 6] save_settings appelé, vertical_mode = {self.vertical_mode}")
        self._do_save()
        self.status_bar.set_success("Configuration complète sauvegardée avec succès !")


if __name__ == '__main__':
    # Forcer le backend FFmpeg (meilleure synchronisation A/V)
    os.environ["QT_MEDIA_BACKEND"] = "ffmpeg"
    app = QApplication(sys.argv)
    viewer = VideoViewer()
    viewer.show()
    sys.exit(app.exec())