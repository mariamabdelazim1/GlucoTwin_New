import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import '../../../core/constants/app_colors.dart';
import '../../../core/constants/app_spacing.dart';
import '../../../core/utils/theme_ext.dart';

// ─────────────────────────────────────────────────────────────────────────────
// Data model
// ─────────────────────────────────────────────────────────────────────────────

class _Doctor {
  const _Doctor({
    required this.initials,
    required this.name,
    required this.specialty,
    required this.hospital,
    required this.rating,
    required this.reviews,
    required this.experience,
    required this.avatarColor,
  });
  final String initials;
  final String name;
  final String specialty;
  final String hospital;
  final double rating;
  final int reviews;
  final int experience;
  final Color avatarColor;
}

const _doctors = [
  _Doctor(
    initials: 'AH',
    name: 'Dr. Ahmed Hassan',
    specialty: 'Endocrinologist · Diabetologist',
    hospital: 'Cairo Diabetes Center, Nasr City',
    rating: 4.8,
    reviews: 124,
    experience: 12,
    avatarColor: Color(0xFF1A6B8A),
  ),
  _Doctor(
    initials: 'SM',
    name: 'Dr. Sara Mahmoud',
    specialty: 'Internal Medicine · Diabetes Specialist',
    hospital: 'Ain Shams University Hospital',
    rating: 4.9,
    reviews: 89,
    experience: 8,
    avatarColor: Color(0xFF7C3AED),
  ),
  _Doctor(
    initials: 'KA',
    name: 'Dr. Khaled Ali',
    specialty: 'Endocrinology · CGM Expert',
    hospital: 'Cleopatra Hospital, Heliopolis',
    rating: 4.7,
    reviews: 201,
    experience: 15,
    avatarColor: Color(0xFF059669),
  ),
  _Doctor(
    initials: 'NF',
    name: 'Dr. Nada Farouk',
    specialty: 'Pediatric & Adult Endocrinology',
    hospital: "Children's Hospital, Dokki",
    rating: 4.6,
    reviews: 67,
    experience: 6,
    avatarColor: Color(0xFFD97706),
  ),
];

// ─────────────────────────────────────────────────────────────────────────────
// Main screen
// ─────────────────────────────────────────────────────────────────────────────

class DoctorScreen extends StatefulWidget {
  const DoctorScreen({super.key});

  @override
  State<DoctorScreen> createState() => _DoctorScreenState();
}

class _DoctorScreenState extends State<DoctorScreen> {
  int _activeIndex = 0;
  bool _showCall = false;

  void _openChat() {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => _ChatPage(doctor: _doctors[_activeIndex]),
      ),
    );
  }

  void _startCall() => setState(() => _showCall = true);
  void _endCall() => setState(() => _showCall = false);

  @override
  Widget build(BuildContext context) {
    final doc = _doctors[_activeIndex];
    return Scaffold(
      backgroundColor: context.appBg,
      body: Stack(
        children: [
          CustomScrollView(
            slivers: [
              SliverAppBar(
                pinned: true,
                backgroundColor: context.appBg,
                automaticallyImplyLeading: false,
                title: const Text('My Doctor',
                    style: TextStyle(fontWeight: FontWeight.w700)),
              ),
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(
                    AppSpacing.screenPadding, 0,
                    AppSpacing.screenPadding, 100),
                sliver: SliverList(
                  delegate: SliverChildListDelegate([
                    _DoctorCard(
                      doctor: doc,
                      onMessage: _openChat,
                      onCall: _startCall,
                    )
                        .animate()
                        .fadeIn(duration: 400.ms)
                        .slideY(begin: 0.1, end: 0),

                    const SizedBox(height: 20),

                    _ChangeDoctorSection(
                      doctors: _doctors,
                      activeIndex: _activeIndex,
                      onSelect: (i) {
                        setState(() => _activeIndex = i);
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                            content: Text(
                                'Doctor changed to ${_doctors[i].name}'),
                            backgroundColor: AppColors.accentGreen,
                          ),
                        );
                      },
                    ).animate(delay: 120.ms).fadeIn(duration: 400.ms),
                  ]),
                ),
              ),
            ],
          ),

          if (_showCall)
            _CallOverlay(doctor: doc, onEnd: _endCall),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Doctor card (assigned doctor)
// ─────────────────────────────────────────────────────────────────────────────

class _DoctorCard extends StatelessWidget {
  const _DoctorCard({
    required this.doctor,
    required this.onMessage,
    required this.onCall,
  });
  final _Doctor doctor;
  final VoidCallback onMessage;
  final VoidCallback onCall;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.cardPadding),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: context.isDark
              ? const [Color(0xFF0D1A35), Color(0xFF0A1220)]
              : [AppColors.primary.withOpacity(0.04), Colors.white],
        ),
        borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
        border: Border.all(color: AppColors.accentCyan.withOpacity(0.25)),
        boxShadow: [
          BoxShadow(
            color: AppColors.accentCyan.withOpacity(0.06),
            blurRadius: 20,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header row
          Row(children: [
            const Icon(Icons.medical_services_rounded,
                color: AppColors.accentCyan, size: 16),
            const SizedBox(width: 6),
            Text('Assigned Doctor',
                style: TextStyle(color: context.textSec, fontSize: 12)),
            const Spacer(),
            Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
              decoration: BoxDecoration(
                color: AppColors.accentGreen.withOpacity(0.12),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(
                    color: AppColors.accentGreen.withOpacity(0.3)),
              ),
              child: const Text('● Active',
                  style: TextStyle(
                      color: AppColors.accentGreen,
                      fontSize: 10,
                      fontWeight: FontWeight.w600)),
            ),
          ]),

          const SizedBox(height: 18),

          // Doctor info row
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Container(
              width: 62,
              height: 62,
              decoration: BoxDecoration(
                color: doctor.avatarColor,
                borderRadius: BorderRadius.circular(18),
              ),
              alignment: Alignment.center,
              child: Text(doctor.initials,
                  style: const TextStyle(
                      color: Colors.white,
                      fontSize: 22,
                      fontWeight: FontWeight.w700)),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(doctor.name,
                        style: TextStyle(
                            color: context.textPri,
                            fontWeight: FontWeight.w700,
                            fontSize: 18)),
                    const SizedBox(height: 3),
                    Text(doctor.specialty,
                        style: TextStyle(
                            color: context.textSec, fontSize: 12)),
                    const SizedBox(height: 5),
                    Row(children: [
                      Icon(Icons.location_on_rounded,
                          color: context.textMut, size: 12),
                      const SizedBox(width: 2),
                      Expanded(
                        child: Text(doctor.hospital,
                            style: TextStyle(
                                color: context.textMut, fontSize: 11)),
                      ),
                    ]),
                    const SizedBox(height: 6),
                    Row(children: [
                      const Icon(Icons.star_rounded,
                          color: Color(0xFFFFB800), size: 14),
                      const SizedBox(width: 3),
                      Text('${doctor.rating}',
                          style: TextStyle(
                              color: context.textPri,
                              fontSize: 12,
                              fontWeight: FontWeight.w600)),
                      const SizedBox(width: 4),
                      Text('(${doctor.reviews} reviews)',
                          style: TextStyle(
                              color: context.textMut, fontSize: 11)),
                      const SizedBox(width: 10),
                      Icon(Icons.work_rounded,
                          color: context.textMut, size: 12),
                      const SizedBox(width: 3),
                      Text('${doctor.experience} yrs',
                          style: TextStyle(
                              color: context.textMut, fontSize: 11)),
                    ]),
                  ]),
            ),
          ]),

          const SizedBox(height: 18),
          Divider(color: context.divC),
          const SizedBox(height: 14),

          // Actions — only Message + Call
          Row(children: [
            _ActionBtn(
              icon: Icons.chat_bubble_rounded,
              label: 'Message',
              color: AppColors.primary,
              onTap: onMessage,
            ),
            const SizedBox(width: 12),
            _ActionBtn(
              icon: Icons.phone_rounded,
              label: 'Call',
              color: AppColors.accentGreen,
              onTap: onCall,
            ),
          ]),
        ],
      ),
    );
  }
}

class _ActionBtn extends StatelessWidget {
  const _ActionBtn({
    required this.icon,
    required this.label,
    required this.color,
    required this.onTap,
  });
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 13),
          decoration: BoxDecoration(
            color: color.withOpacity(0.1),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: color.withOpacity(0.25)),
          ),
          child: Column(children: [
            Icon(icon, color: color, size: 22),
            const SizedBox(height: 5),
            Text(label,
                style: TextStyle(
                    color: color,
                    fontSize: 12,
                    fontWeight: FontWeight.w600)),
          ]),
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Change doctor section
// ─────────────────────────────────────────────────────────────────────────────

class _ChangeDoctorSection extends StatelessWidget {
  const _ChangeDoctorSection({
    required this.doctors,
    required this.activeIndex,
    required this.onSelect,
  });
  final List<_Doctor> doctors;
  final int activeIndex;
  final ValueChanged<int> onSelect;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.cardPadding),
      decoration: BoxDecoration(
        color: context.cardBg,
        borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
        border: Border.all(color: context.borderC),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            const Icon(Icons.swap_horiz_rounded,
                color: AppColors.primary, size: 18),
            const SizedBox(width: 8),
            Text('Change Doctor',
                style: TextStyle(
                    color: context.textPri,
                    fontWeight: FontWeight.w600,
                    fontSize: 14)),
          ]),
          const SizedBox(height: 4),
          Text('Select a doctor from the available care team.',
              style: TextStyle(
                  color: context.textSec, fontSize: 12, height: 1.4)),
          const SizedBox(height: 16),
          ...List.generate(doctors.length, (i) {
            final isActive = i == activeIndex;
            final doc = doctors[i];
            return Padding(
              padding:
                  EdgeInsets.only(bottom: i < doctors.length - 1 ? 10 : 0),
              child: GestureDetector(
                onTap: isActive ? null : () => onSelect(i),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 200),
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: isActive
                        ? AppColors.primary.withOpacity(0.08)
                        : context.appBg,
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(
                      color: isActive
                          ? AppColors.primary.withOpacity(0.4)
                          : context.borderC,
                      width: isActive ? 1.5 : 1,
                    ),
                  ),
                  child: Row(children: [
                    Container(
                      width: 44,
                      height: 44,
                      decoration: BoxDecoration(
                        color: doc.avatarColor,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      alignment: Alignment.center,
                      child: Text(doc.initials,
                          style: const TextStyle(
                              color: Colors.white,
                              fontSize: 14,
                              fontWeight: FontWeight.w700)),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(children: [
                            Expanded(
                              child: Text(doc.name,
                                  style: TextStyle(
                                      color: context.textPri,
                                      fontWeight: FontWeight.w600,
                                      fontSize: 13)),
                            ),
                            if (isActive)
                              Container(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 7, vertical: 2),
                                decoration: BoxDecoration(
                                  color:
                                      AppColors.primary.withOpacity(0.12),
                                  borderRadius: BorderRadius.circular(6),
                                ),
                                child: const Text('Current',
                                    style: TextStyle(
                                        color: AppColors.primary,
                                        fontSize: 9,
                                        fontWeight: FontWeight.w600)),
                              ),
                          ]),
                          const SizedBox(height: 2),
                          Text(doc.specialty,
                              style: TextStyle(
                                  color: context.textMut, fontSize: 11)),
                          const SizedBox(height: 3),
                          Row(children: [
                            const Icon(Icons.star_rounded,
                                color: Color(0xFFFFB800), size: 12),
                            const SizedBox(width: 2),
                            Text('${doc.rating}  ·  ${doc.experience} yrs',
                                style: TextStyle(
                                    color: context.textMut,
                                    fontSize: 11)),
                          ]),
                        ],
                      ),
                    ),
                    const SizedBox(width: 8),
                    if (!isActive)
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 12, vertical: 6),
                        decoration: BoxDecoration(
                          color: AppColors.primary.withOpacity(0.1),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(
                              color: AppColors.primary.withOpacity(0.3)),
                        ),
                        child: const Text('Select',
                            style: TextStyle(
                                color: AppColors.primary,
                                fontSize: 11,
                                fontWeight: FontWeight.w600)),
                      ),
                  ]),
                ),
              ),
            );
          }),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Call overlay
// ─────────────────────────────────────────────────────────────────────────────

class _CallOverlay extends StatefulWidget {
  const _CallOverlay({required this.doctor, required this.onEnd});
  final _Doctor doctor;
  final VoidCallback onEnd;

  @override
  State<_CallOverlay> createState() => _CallOverlayState();
}

class _CallOverlayState extends State<_CallOverlay> {
  late Timer _timer;
  int _seconds = 0;
  bool _connected = false;
  bool _muted = false;
  bool _speaker = false;

  @override
  void initState() {
    super.initState();
    // Simulate connecting after 2s
    Future.delayed(const Duration(seconds: 2), () {
      if (mounted) setState(() => _connected = true);
    });
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted && _connected) setState(() => _seconds++);
    });
  }

  @override
  void dispose() {
    _timer.cancel();
    super.dispose();
  }

  String get _timeLabel {
    final m = (_seconds ~/ 60).toString().padLeft(2, '0');
    final s = (_seconds % 60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.black.withOpacity(0.92),
      child: SafeArea(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            // Avatar
            Container(
              width: 100,
              height: 100,
              decoration: BoxDecoration(
                color: widget.doctor.avatarColor,
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(
                    color: widget.doctor.avatarColor.withOpacity(0.4),
                    blurRadius: 30,
                    spreadRadius: 5,
                  ),
                ],
              ),
              alignment: Alignment.center,
              child: Text(
                widget.doctor.initials,
                style: const TextStyle(
                    color: Colors.white,
                    fontSize: 36,
                    fontWeight: FontWeight.w700),
              ),
            )
                .animate(onPlay: (c) => c.repeat(reverse: true))
                .scaleXY(begin: 1.0, end: 1.05, duration: 1200.ms),

            const SizedBox(height: 28),

            Text(
              widget.doctor.name,
              style: const TextStyle(
                  color: Colors.white,
                  fontSize: 22,
                  fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 6),
            Text(
              widget.doctor.specialty,
              style: const TextStyle(
                  color: Color(0xFFAAAAAA), fontSize: 14),
            ),
            const SizedBox(height: 12),
            Text(
              _connected ? _timeLabel : 'Connecting...',
              style: TextStyle(
                color: _connected
                    ? AppColors.accentGreen
                    : const Color(0xFF888888),
                fontSize: 18,
                fontWeight: FontWeight.w600,
                letterSpacing: 2,
              ),
            ),

            const SizedBox(height: 60),

            // Controls row
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                _CallBtn(
                  icon: _muted ? Icons.mic_off_rounded : Icons.mic_rounded,
                  label: _muted ? 'Unmute' : 'Mute',
                  color: _muted ? AppColors.warning : const Color(0xFF333333),
                  onTap: () => setState(() => _muted = !_muted),
                ),
                const SizedBox(width: 24),
                // End call button
                GestureDetector(
                  onTap: widget.onEnd,
                  child: Container(
                    width: 70,
                    height: 70,
                    decoration: BoxDecoration(
                      color: AppColors.danger,
                      shape: BoxShape.circle,
                      boxShadow: [
                        BoxShadow(
                          color: AppColors.danger.withOpacity(0.4),
                          blurRadius: 20,
                          spreadRadius: 2,
                        ),
                      ],
                    ),
                    child: const Icon(Icons.call_end_rounded,
                        color: Colors.white, size: 32),
                  ),
                ),
                const SizedBox(width: 24),
                _CallBtn(
                  icon: _speaker
                      ? Icons.volume_up_rounded
                      : Icons.volume_down_rounded,
                  label: 'Speaker',
                  color: _speaker
                      ? AppColors.primary
                      : const Color(0xFF333333),
                  onTap: () => setState(() => _speaker = !_speaker),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _CallBtn extends StatelessWidget {
  const _CallBtn({
    required this.icon,
    required this.label,
    required this.color,
    required this.onTap,
  });
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Column(children: [
        Container(
          width: 54,
          height: 54,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          child: Icon(icon, color: Colors.white, size: 24),
        ),
        const SizedBox(height: 8),
        Text(label,
            style: const TextStyle(color: Color(0xFFAAAAAA), fontSize: 11)),
      ]),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Chat page
// ─────────────────────────────────────────────────────────────────────────────

class _ChatMsg {
  _ChatMsg(
      {required this.text, required this.isDoctor, required this.time});
  final String text;
  final bool isDoctor;
  final String time;
}

class _ChatPage extends StatefulWidget {
  const _ChatPage({required this.doctor});
  final _Doctor doctor;

  @override
  State<_ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<_ChatPage> {
  final _msgCtrl = TextEditingController();
  final _scrollCtrl = ScrollController();
  final List<_ChatMsg> _msgs = [
    _ChatMsg(
      text: 'Hello! I reviewed your latest glucose readings from GlucoTwin. Your overnight control looks good.',
      isDoctor: true,
      time: '10:30 AM',
    ),
    _ChatMsg(
      text: 'Good morning Doctor! My post-meal spikes have been high lately — reaching 220–240.',
      isDoctor: false,
      time: '10:32 AM',
    ),
    _ChatMsg(
      text: 'I noticed that too. Let\'s adjust your bolus carb ratio from 1:10 to 1:8 for lunch and monitor for 3 days. Keep logging everything.',
      isDoctor: true,
      time: '10:35 AM',
    ),
    _ChatMsg(
      text: 'Should I adjust my correction factor too?',
      isDoctor: false,
      time: '10:36 AM',
    ),
    _ChatMsg(
      text: 'Not yet — change the carb ratio first and see how it responds. I can review your Digital Twin data remotely anytime.',
      isDoctor: true,
      time: '10:38 AM',
    ),
  ];

  String get _now {
    final t = DateTime.now();
    final h = t.hour > 12 ? t.hour - 12 : (t.hour == 0 ? 12 : t.hour);
    final m = t.minute.toString().padLeft(2, '0');
    return '$h:$m ${t.hour >= 12 ? 'PM' : 'AM'}';
  }

  void _send() {
    final text = _msgCtrl.text.trim();
    if (text.isEmpty) return;
    setState(() {
      _msgs.add(_ChatMsg(text: text, isDoctor: false, time: _now));
    });
    _msgCtrl.clear();
    _scrollBottom();

    // Auto-reply after 1.5s
    Future.delayed(const Duration(milliseconds: 1500), () {
      if (!mounted) return;
      setState(() {
        _msgs.add(_ChatMsg(
          text: 'Thank you for the update. I\'ll review your readings and get back to you shortly.',
          isDoctor: true,
          time: _now,
        ));
      });
      _scrollBottom();
    });
  }

  void _scrollBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(
          _scrollCtrl.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  void dispose() {
    _msgCtrl.dispose();
    _scrollCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: context.appBg,
      appBar: AppBar(
        backgroundColor: context.appBg,
        titleSpacing: 0,
        title: Row(children: [
          Container(
            width: 38,
            height: 38,
            decoration: BoxDecoration(
              color: widget.doctor.avatarColor,
              borderRadius: BorderRadius.circular(11),
            ),
            alignment: Alignment.center,
            child: Text(widget.doctor.initials,
                style: const TextStyle(
                    color: Colors.white,
                    fontSize: 13,
                    fontWeight: FontWeight.w700)),
          ),
          const SizedBox(width: 10),
          Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(widget.doctor.name,
                style: TextStyle(
                    color: context.textPri,
                    fontSize: 14,
                    fontWeight: FontWeight.w700)),
            Row(children: [
              Container(
                  width: 6,
                  height: 6,
                  decoration: const BoxDecoration(
                      color: AppColors.accentGreen,
                      shape: BoxShape.circle)),
              const SizedBox(width: 4),
              const Text('Online',
                  style: TextStyle(
                      fontSize: 11, color: AppColors.accentGreen)),
            ]),
          ]),
        ]),
      ),
      body: Column(
        children: [
          // Messages
          Expanded(
            child: ListView.builder(
              controller: _scrollCtrl,
              padding: const EdgeInsets.symmetric(
                  horizontal: 16, vertical: 12),
              itemCount: _msgs.length,
              itemBuilder: (_, i) => _Bubble(
                msg: _msgs[i],
                doctorColor: widget.doctor.avatarColor,
                doctorInitials: widget.doctor.initials,
              ),
            ),
          ),

          // Input bar
          Container(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 16),
            decoration: BoxDecoration(
              color: context.cardBg,
              border: Border(top: BorderSide(color: context.borderC)),
            ),
            child: Row(children: [
              Expanded(
                child: TextField(
                  controller: _msgCtrl,
                  textInputAction: TextInputAction.send,
                  onSubmitted: (_) => _send(),
                  style: TextStyle(
                      color: context.textPri, fontSize: 14),
                  decoration: const InputDecoration(
                    hintText: 'Type a message...',
                    border: InputBorder.none,
                    enabledBorder: InputBorder.none,
                    focusedBorder: InputBorder.none,
                    filled: false,
                    contentPadding: EdgeInsets.symmetric(
                        horizontal: 4, vertical: 8),
                  ),
                ),
              ),
              GestureDetector(
                onTap: _send,
                child: Container(
                  width: 42,
                  height: 42,
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                        colors: AppColors.primaryGradient),
                    borderRadius: BorderRadius.circular(13),
                  ),
                  child: const Icon(Icons.send_rounded,
                      color: Colors.white, size: 18),
                ),
              ),
            ]),
          ),
        ],
      ),
    );
  }
}

class _Bubble extends StatelessWidget {
  const _Bubble({
    required this.msg,
    required this.doctorColor,
    required this.doctorInitials,
  });
  final _ChatMsg msg;
  final Color doctorColor;
  final String doctorInitials;

  @override
  Widget build(BuildContext context) {
    final isDoc = msg.isDoctor;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        mainAxisAlignment:
            isDoc ? MainAxisAlignment.start : MainAxisAlignment.end,
        children: [
          if (isDoc) ...[
            Container(
              width: 30,
              height: 30,
              decoration: BoxDecoration(
                  color: doctorColor,
                  borderRadius: BorderRadius.circular(9)),
              alignment: Alignment.center,
              child: Text(doctorInitials,
                  style: const TextStyle(
                      color: Colors.white,
                      fontSize: 10,
                      fontWeight: FontWeight.w700)),
            ),
            const SizedBox(width: 8),
          ],
          Flexible(
            child: Column(
              crossAxisAlignment: isDoc
                  ? CrossAxisAlignment.start
                  : CrossAxisAlignment.end,
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 14, vertical: 10),
                  decoration: BoxDecoration(
                    color: isDoc
                        ? context.cardBg
                        : AppColors.primary,
                    borderRadius: BorderRadius.only(
                      topLeft: const Radius.circular(16),
                      topRight: const Radius.circular(16),
                      bottomLeft:
                          Radius.circular(isDoc ? 4 : 16),
                      bottomRight:
                          Radius.circular(isDoc ? 16 : 4),
                    ),
                    border: isDoc
                        ? Border.all(color: context.borderC)
                        : null,
                  ),
                  child: Text(
                    msg.text,
                    style: TextStyle(
                      color: isDoc ? context.textPri : Colors.white,
                      fontSize: 13,
                      height: 1.4,
                    ),
                  ),
                ),
                const SizedBox(height: 3),
                Text(msg.time,
                    style: TextStyle(
                        color: context.textMut, fontSize: 10)),
              ],
            ),
          ),
          if (!isDoc) const SizedBox(width: 8),
        ],
      ),
    );
  }
}
