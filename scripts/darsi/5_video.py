#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ÉTAPE 5 — Montage de la vidéo YouTube (1080p)
==============================================
Layout : image du cheikh à GAUCHE / page réelle du livre à DROITE.
Surlignage : rectangle jaune semi-transparent sur la LIGNE en cours,
piloté par sendcmd + drawbox (un seul filtre pour toute la vidéo).

Pages : assemblées par concat (chaque page apparaît au moment de sa
première ligne lue). Audio : fichier source du cheikh.

Usage :
  python 5_video.py --page-fin 23        (limiter aux pages couvertes)
"""
import argparse
import json
import os
import shlex
import subprocess

DOS = "/home/z/my-project/travail/darsi1"
CHEIKH = "/home/z/my-project/upload/IMAGE.jpeg"
AUDIO = "/home/z/my-project/upload/Audio darsi-1.mpeg"

W, H = 1920, 1080
LPAGE = 834                       # largeur panneau livre (612/792 × 1080)
XPAGE = W - LPAGE                 # 1086
EC = H / 792.0                    # pt PDF → px

MARGE_X, MARGE_Y = 8, 5           # expansion du rectangle surligneur


def charger_lignes(page_fin=None):
    lignes = json.load(open(f"{DOS}/lignes_timing.json", encoding="utf-8"))
    lignes.sort(key=lambda L: (L["page"], L["n"]))
    if page_fin:
        lignes = [L for L in lignes if L["page"] <= page_fin]
    return lignes


def segments_lignes(lignes, duree):
    """Segment [t_debut, t_fin] pour chaque ligne (de son debut au debut
    de la suivante) ; ordre chronologique."""
    evts = sorted(lignes, key=lambda L: L["debut"])
    segs = []
    for k, L in enumerate(evts):
        fin = evts[k + 1]["debut"] if k + 1 < len(evts) else min(duree,
                                                                 L["fin"] + 30)
        if fin <= L["debut"]:
            fin = L["debut"] + 1.0
        segs.append((L, L["debut"], fin))
    return segs


def ecrire_sendcmd(segs, chemin, debut=0.0, fin=None):
    """Fichier de commandes pour la fenêtre [debut, fin) ; temps relatifs.
    La ligne active au début de la fenêtre est appliquée dès t=0."""
    if fin is None:
        fin = float("inf")
    avec = [(L, t0, t1) for L, t0, t1 in segs if t0 < fin and t1 > debut]
    with open(chemin, "w", encoding="utf-8") as f:
        if avec and avec[0][1] > debut:
            # état initial : rect de la ligne déjà active à `debut`
            L = avec[0][0]
            x0, y0, x1, y1 = L["bbox"]
            x = int(XPAGE + x0 * EC) - MARGE_X
            y = max(0, int(y0 * EC) - MARGE_Y)
            w = int((x1 - x0) * EC) + 2 * MARGE_X
            h = int((y1 - y0) * EC) + 2 * MARGE_Y
            f.write(f"0.050 [enter] drawbox x {x}, drawbox y {y}, "
                    f"drawbox w {w}, drawbox h {h};\n")
        for L, t0, _ in avec:
            x0, y0, x1, y1 = L["bbox"]
            x = max(0, int(XPAGE + x0 * EC) - MARGE_X)
            y = max(0, int(y0 * EC) - MARGE_Y)
            w = int((x1 - x0) * EC) + 2 * MARGE_X
            h = int((y1 - y0) * EC) + 2 * MARGE_Y
            t_rel = max(0.051, t0 - debut)
            cmds = (f"drawbox x {x}, drawbox y {y}, "
                    f"drawbox w {w}, drawbox h {h}")
            f.write(f"{t_rel:.3f} [enter] {cmds};\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page-fin", type=int, default=None,
                    help="dernière page à montrer (pages couvertes)")
    ap.add_argument("--sortie",
                    default="/home/z/my-project/download/darsi1/"
                            "Darsi1_Maki_wa_Madani.mp4")
    ap.add_argument("--crf", type=int, default=20)
    ap.add_argument("--apercu-secondes", type=float, default=None,
                    help="ne rendre que les N premières secondes (test)")
    ap.add_argument("--debut", type=float, default=0.0,
                    help="début du rendu (s) — rendu par tranches")
    ap.add_argument("--fin", type=float, default=None,
                    help="fin du rendu (s) — rendu par tranches")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.sortie), exist_ok=True)

    # durée audio
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of",
                        "default=noprint_wrappers=1:nokey=1", AUDIO],
                       capture_output=True, text=True)
    duree_totale = float(r.stdout.strip())
    debut = max(0.0, args.debut)
    fin = min(duree_totale, args.fin) if args.fin else duree_totale
    duree = fin - debut
    if args.apercu_secondes:
        duree = min(duree, args.apercu_secondes)
        fin = debut + duree

    lignes = charger_lignes(args.page_fin)
    segs = segments_lignes(lignes, duree_totale)

    # ---- segments de pages (fenêtre [debut, fin]) --------------------------
    pages_ordre = []
    bornes = []                 # (page, ps, pe) fenêtres globales
    for L in lignes:
        p = L["page"]
        if p not in pages_ordre:
            pages_ordre.append(p)
    for p in pages_ordre:
        ps = max(0.0, min(L["debut"] for L in lignes if L["page"] == p) - 0.35)
        bornes.append((p, ps))
    # pe = début de la page suivante (ou fin globale)
    fenetres = []
    for k, (p, ps) in enumerate(bornes):
        pe = bornes[k + 1][1] if k + 1 < len(bornes) else duree_totale
        vi = max(ps, debut)
        ve = min(pe, fin)
        if ve - vi > 0.5:
            fenetres.append((p, ve - vi))
    pages_ordre = [p for p, _ in fenetres]
    durs = [d for _, d in fenetres]
    if not pages_ordre:
        pages_ordre, durs = [1], [duree]
    print(f"Pages affichées : {pages_ordre} "
          f"({len(pages_ordre)} pages, {duree/60:.1f} min)", flush=True)

    # ---- fichier sendcmd ----------------------------------------------------
    cmdfile = f"{DOS}/sendcmd.txt"
    ecrire_sendcmd(segs, cmdfile, debut, fin)
    print(f"{len(segs)} segments de surlignage → {cmdfile}", flush=True)

    # ---- commande ffmpeg ----------------------------------------------------
    fc = []
    inputs = []
    # pages (boucle infinie limitée par trim dans le graphe)
    for k, p in enumerate(pages_ordre):
        inputs += ["-loop", "1", "-framerate", "25",
                   "-i", f"{DOS}/pages/page_{p:02d}.png"]
    n_pages = len(pages_ordre)
    # cheikh
    inputs += ["-loop", "1", "-framerate", "25", "-i", CHEIKH]
    i_cheikh = n_pages
    # audio (seek au début de la tranche)
    inputs += ["-ss", f"{debut:.3f}", "-i", AUDIO]

    # filtre : pages → trim → concat
    for k in range(n_pages):
        fc.append(f"[{k}:v]trim=duration={durs[k]:.3f},setpts=PTS-STARTPTS,"
                  f"scale={LPAGE}:{H}:flags=lanczos,setsar=1,fps=25,"
                  f"format=yuv420p[p{k}]")
    chaine = "".join(f"[p{k}]" for k in range(n_pages))
    fc.append(f"{chaine}concat=n={n_pages}:v=1:a=0[pages]")
    # cheikh → cadre gauche
    fc.append(f"[{i_cheikh}:v]trim=duration={duree:.3f},setpts=PTS-STARTPTS,"
              f"scale={XPAGE}:{H}:force_original_aspect_ratio="
              f"decrease:flags=lanczos,pad={XPAGE}:{H}:(ow-iw)/2:(oh-ih)/2:"
              f"color=0x14161A,setsar=1,fps=25,format=yuv420p[ch]")
    fc.append("[ch][pages]hstack=inputs=2[base]")
    fc.append("[base]sendcmd=f=" + shlex.quote(cmdfile) +
              ",drawbox=x=0:y=0:w=0:h=0:color=0xFFCC00@0.40:t=fill[vid]")

    script = f"{DOS}/filtergraph.txt"
    with open(script, "w", encoding="utf-8") as f:
        f.write(";\n".join(fc))

    cmd = ["ffmpeg", "-y", "-v", "error", "-stats", "-nostdin"]
    cmd += inputs
    cmd += ["-filter_complex_script", script,
            "-map", "[vid]", "-map", f"{n_pages + 1}:a",
            "-t", f"{duree:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", str(args.crf),
            "-tune", "stillimage", "-pix_fmt", "yuv420p", "-r", "25",
            "-c:a", "aac", "-b:a", "64k", "-ar", "44100", "-ac", "1",
            "-movflags", "+faststart",
            args.sortie]
    print("Lancement ffmpeg (rendu ~long)...", flush=True)
    subprocess.run(cmd, check=True)
    print(f"✔ vidéo → {args.sortie}", flush=True)


if __name__ == "__main__":
    main()
