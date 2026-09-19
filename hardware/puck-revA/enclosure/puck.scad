// The puck's shell: one board, several bodies.
//
// design/puck/Shape.dc.html deliberately refuses to choose a form factor, and docs/puck-hardware.md
// makes that refusal affordable: one PCB with a USB-C inlet, and the shell as the only variable.
// This file is that variable. `variant` swaps the base; everything above the PCB stays identical, so
// the three bodies are genuinely comparable when somebody lives with each for a week.
//
// WHAT IS LOAD-BEARING HERE, and why each number is what it is:
//
//   * standoff (9 mm), measured from the EMITTER FACE and not from the PCB -- the LED body is
//     1.6 mm of that and leaving it out costs you most of the tolerance. docs/puck-hardware.md:
//     closer than 8-10 mm and you see three distinct hotspots through the wall. At the default
//     led_ring_d the emitters also sit 8.4 mm in from the side wall, so the vertical and radial
//     path lengths come out deliberately close -- a glow that is even from the top AND from the
//     side is the whole point of a body whose orientation nobody can predict.
//   * diff_wall (2.0 mm). The doc allows 1.2-2.0. Uniform 2.0 rather than a thin top and a thick
//     skirt, because a step in wall thickness is a step in brightness, and it shows.
//   * The joint sits above the connector, not at the PCB plane, and the skirt belongs to the
//     DIFFUSER rather than the base. The board is 50 mm and has to drop into the base from above,
//     so anything the base sticks up would have to be wider than the bore it is standing in --
//     which cannot be built. Putting the skirt on the diffuser costs a few millimeters of glowing
//     band and buys a connector opening that is a notch in an opaque rim: no bridging, no supports.
//   * boss_angles avoid the antenna. Non-negotiable, and asserted below rather than commented.
//
// PRINTING. Base: any color, 0.4 mm nozzle, 0.2 mm layers, 3 perimeters, 20% infill.
//
// Diffuser: WHITE or NATURAL PLA, 0.2 mm layers, 4+ perimeters, 100% infill in the roof -- the
// diffuser's job is to be solid plastic, and gaps between perimeters read as stripes in the glow.
// **Print it ROOF-DOWN.** Two reasons and both matter: the step where the skirt meets the body
// becomes an upward-facing shoulder instead of a 2.25 mm overhang that droops, and the lit face is
// then laid against the bed, which is the flattest and most uniform surface the printer can make.
// A textured bed gives that face a diffuse matte it would otherwise need sanding for.
//
// NOT IN THIS FILE, on purpose: an opening for the expansion header. Rev A populates the header and
// the shell still does not expose it (docs/puck-hardware.md). Reaching it means taking the shell off.

/* [Which shell] */
variant = "shelf";      // [shelf, tail, dock]
show    = "assembly";   // [assembly, base, diffuser, board, section]

/* [The board it holds] */
board_d     = 50;    // PCB outside diameter
board_t     = 1.6;
bolt_circle = 42;    // 3x M2, frozen with the board outline; see gen_pcb.py for why 42 not 40
board_clear = 0.4;   // radial slop around the PCB

/* [Light] */
led_ring_d = 34;     // circle the FOUR SK6812s sit on -- four, because three will not place
led_h      = 1.6;    // SK6812 5050 body height -- the emitter face, not the PCB, is the datum
standoff   = 9;      // emitter face to the inner surface of the diffuser's top
diff_wall  = 2.0;

/* [Shell] */
wall      = 2.0;
floor_t   = 1.6;
boss_h    = 4.0;     // M2 self-tappers want ~4 mm of engagement
boss_d    = 5.0;
boss_hole = 1.6;     // pilot for an M2 self-tapper into PLA
fit_clear = 0.25;    // FDM press fit; loosen to 0.35 if your printer runs fat
lip_h     = 4.0;

/* [Openings] */
usb_w     = 9.6;
usb_h     = 3.8;
btn_d     = 3.6;
btn_angle = 75;

/* [Angles] */
conn_angle      = 0;    // USB-C, and the cable exit on the tail variant
antenna_angle   = 180;  // the module's antenna overhangs the board edge here
antenna_keepout = 30;   // +/- degrees that must stay free of bosses, magnets, metal

/* [Dock variant] */
magnet_d = 6.2;
magnet_t = 3.2;
magnet_angles = [110, 290];

/* [Tail variant] */
tie_tab_w   = 12.0;    // tangential width of the strain-relief tab
tie_tab_r   = 7.0;     // how far it reaches radially
tie_tab_h   = 5.0;     // stays well under base_h; a tab that reaches the joint fouls the diffuser
tie_slot_w  = 2.2;
tie_slot_h  = 2.4;

/* [Render] */
$fn = 96;

// ---- derived ---------------------------------------------------------------------------------

outer_d   = board_d + 2 * board_clear + 2 * wall;
inner_d   = outer_d - 2 * wall;
pcb_z     = floor_t + boss_h;          // underside of the PCB
pcb_top   = pcb_z + board_t;           // the joint plane, and the datum for everything lit
diff_top  = pcb_top + led_h + standoff; // inner face of the diffuser's roof
total_h   = diff_top + diff_wall;
base_h    = pcb_top + lip_h;           // joint plane, deliberately above the connector
skirt_z   = pcb_top + 0.8;             // skirt starts clear of board-edge components
skirt_od  = inner_d - 2 * fit_clear;   // the diffuser's skirt drops INSIDE the base
skirt_id  = skirt_od - 2 * diff_wall;

boss_angles = [24, 144, 264];   // solved against the board, not chosen

// The one rule that cannot be negotiated, checked rather than trusted. Anything solid and
// especially anything metal within the keepout detunes the antenna, and the symptom is FAR
// breathing red in rooms where a devkit was fine.
module keepout_check(angles, what) {
    for (a = angles) {
        d = abs(((a - antenna_angle + 180) % 360) - 180);
        assert(d > antenna_keepout, str(what, " at ", a, " deg is ", d,
               " deg from the antenna; needs more than ", antenna_keepout));
    }
}
keepout_check(boss_angles, "mounting boss");
keepout_check(magnet_angles, "magnet");

// Bosses and magnet pockets share a floor and are solved on different circles, so their angles alone
// do not tell you whether they touch. Check the actual distance.
module spacing_check() {
    for (b = boss_angles) for (m = magnet_angles) {
        bx = (bolt_circle/2) * cos(b); by = (bolt_circle/2) * sin(b);
        mx = (bolt_circle/2 - 4) * cos(m); my = (bolt_circle/2 - 4) * sin(m);
        d = sqrt(pow(bx-mx,2) + pow(by-my,2));
        need = boss_d/2 + magnet_d/2 + wall + 0.6;
        assert(d > need, str("boss ", b, " and magnet ", m, " are ", d, " mm apart; need ", need));
    }
}
spacing_check();

module at(angle, r, z = 0) {
    rotate([0, 0, angle]) translate([r, 0, z]) children();
}

module tube(od, id, h) {
    difference() { cylinder(d = od, h = h); translate([0,0,-1]) cylinder(d = id, h = h + 2); }
}

// The connector notch, cut through both the diffuser's skirt and the base's spigot so the two
// agree. Generous in Z on purpose: it is a notch open at the bottom, so extra height costs nothing
// and a connector that fouls its opening is a board you cannot plug in.
module usb_cut() {
    at(conn_angle, 0) translate([0, 0, pcb_top - 0.01])
        translate([outer_d/4, 0, usb_h/2]) cube([outer_d/2 + 2, usb_w, usb_h], center = true);
}

module button_cut() {
    at(btn_angle, outer_d/2, pcb_top + 1.5) rotate([0, 90, 0])
        cylinder(d = btn_d, h = wall * 3, center = true);
}

// ---- the parts -------------------------------------------------------------------------------

module base_common() {
    difference() {
        cylinder(d = outer_d, h = base_h);
        translate([0, 0, floor_t]) cylinder(d = inner_d, h = base_h);
        usb_cut();
        button_cut();
    }
    // Bosses, and the shelf the PCB actually rests on.
    for (a = boss_angles)
        at(a, bolt_circle/2) difference() {
            cylinder(d = boss_d, h = pcb_z);
            translate([0, 0, floor_t]) cylinder(d = boss_hole, h = pcb_z);
        }
}

module base_shelf() {
    base_common();
    // Three feet, off the boss angles so the load does not go straight into a screw.
    for (a = [60, 180, 300]) at(a, outer_d/2 - 6) cylinder(d = 6, h = 0.8);
}

// Strain relief, and NOT a captive cable. Rev A is a test board and nobody solders a lead to one,
// so the cable is an ordinary USB-C lead and this is a tie-down: a zip tie through the slot takes
// the pull off the connector, which is the part that tears off when somebody yanks a puck out of a
// socket by its cable. It also has to stay under the joint plane -- a molded collar centered on the
// connector cannot, because the connector sits 8.8 mm up and the base ends at 11.2.
module base_tail() {
    base_common();
    difference() {
        at(conn_angle, outer_d/2 - 2 + tie_tab_r/2, 0)
            translate([0, 0, tie_tab_h/2]) cube([tie_tab_r + 4, tie_tab_w, tie_tab_h], center = true);
        at(conn_angle, outer_d/2 + 1.5, 0)
            translate([0, 0, tie_tab_h/2]) cube([tie_slot_w, tie_tab_w + 4, tie_slot_h], center = true);
    }
}

module base_dock() {
    difference() {
        union() {
            base_common();
            // The floor is 1.6 mm and a magnet is 3.2, so a pocket sunk straight into it breaks
            // through into the board cavity. Each magnet gets its own raised boss instead, tall
            // enough to close over the magnet and still clear the underside of the PCB.
            for (a = magnet_angles)
                at(a, bolt_circle/2 - 2) cylinder(d = magnet_d + 2 * wall, h = magnet_t + 1.0);
        }
        for (a = magnet_angles)
            at(a, bolt_circle/2 - 2, -0.01) cylinder(d = magnet_d, h = magnet_t);
        // A shallow relief for the dock's pogo pads to land in.
        translate([0, 0, -0.01]) cylinder(d = 22, h = 0.6);
    }
}

module base() {
    if      (variant == "tail")  base_tail();
    else if (variant == "dock")  base_dock();
    else                         base_shelf();
}

// The lit part: a uniform 2 mm wall, a closed roof, and a skirt that drops inside the base's bore.
// The two bores differ on purpose -- the body's keeps the wall at 2 mm, the skirt's keeps it at 2 mm
// against a smaller outside diameter. One bore for both would make the body wall 4.25 mm and the
// glow would die in it.
module diffuser() {
    difference() {
        union() {
            translate([0, 0, base_h]) cylinder(d = outer_d, h = total_h - base_h);
            translate([0, 0, skirt_z]) cylinder(d = skirt_od, h = base_h - skirt_z);
        }
        translate([0, 0, base_h - 0.01]) cylinder(d = inner_d, h = diff_top - base_h + 0.01);
        translate([0, 0, skirt_z - 0.01]) cylinder(d = skirt_id, h = base_h - skirt_z + 0.02);
        usb_cut();
    }
}

module board_mock() {
    color("#2d6a4f") translate([0, 0, pcb_z]) cylinder(d = board_d, h = board_t);
    // the four emitters, where the standoff is measured from (gen_pcb.py solves the angles)
    for (a = [43, 128, 232, 317])
        color("#fff1d8") at(a, led_ring_d/2, pcb_top) cylinder(d = 5, h = 1.6);
    // the module, lying with its antenna end over the board edge
    color("#1b1d23") at(antenna_angle, board_d/2 - 12.75, pcb_top + 1.55)
        cube([25.5, 18, 3.1], center = true);
}

// ---- what to render --------------------------------------------------------------------------

if (show == "base")          base();
else if (show == "diffuser") diffuser();
else if (show == "board")    board_mock();
else if (show == "section")  difference() {
    union() { color("#8f939c") base(); color("#f0e6d2", 0.75) diffuser(); board_mock(); }
    translate([0, -outer_d, -1]) cube([outer_d, outer_d * 2, total_h + 2]);
}
else {
    color("#8f939c") base();
    color("#f0e6d2", 0.55) diffuser();
    board_mock();
}
