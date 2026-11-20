import 'dart:async';
import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import 'core/constants/app_colors.dart';
import 'data/sync_api.dart';
import 'presentation/widgets/bolus_recommendation_card.dart';
import 'presentation/widgets/portal_message_bubble.dart';

const green = AppColors.portalBlue;
const darkGreen = AppColors.portalNavy;
const background = AppColors.portalBackground;
const muted = AppColors.portalMuted;
const dashboardCyan = Color(0xFF22B8D6);
const dashboardIce = AppColors.portalIceBlue;
const dashboardBorder = AppColors.portalBorder;
const authNavy = Color(0xFF072E50);
const authNavyDeep = Color(0xFF061F39);
const authBlue = Color(0xFF237BB6);
const authBlueDark = Color(0xFF175F91);
const authIce = Color(0xFFE1F0FA);
const authIceText = Color(0xFFD3E7F4);
const authBorder = Color(0xFFD7E8F3);

double doctorRank(Map<String, dynamic> doctor) {
  final rating = doctor['rating'] as Map<String, dynamic>? ?? {};
  final profile = doctor['doctorProfile'] as Map<String, dynamic>? ?? {};
  final average = (rating['average'] as num?)?.toDouble() ?? 0;
  final years =
      (double.tryParse('${profile['yearsExperience'] ?? 0}') ?? 0).clamp(0, 20);
  return (average / 5) * 0.7 + (years / 20) * 0.3;
}

String _profileText(dynamic value) {
  final text = value?.toString() ?? '';
  return text.isEmpty ? 'Not provided' : text;
}

int compareConversationMessages(
    Map<String, dynamic> left, Map<String, dynamic> right) {
  final leftTime = DateTime.tryParse('${left['sentAt'] ?? ''}')
          ?.toUtc()
          .microsecondsSinceEpoch ??
      0;
  final rightTime = DateTime.tryParse('${right['sentAt'] ?? ''}')
          ?.toUtc()
          .microsecondsSinceEpoch ??
      0;
  return leftTime.compareTo(rightTime) != 0
      ? leftTime.compareTo(rightTime)
      : '${left['id'] ?? ''}'.compareTo('${right['id'] ?? ''}');
}

List<Map<String, dynamic>> chronologicalConversationMessages(dynamic rows) {
  final messages = ((rows as List?) ?? [])
      .map((value) => Map<String, dynamic>.from(value as Map))
      .toList();
  messages.sort(compareConversationMessages);
  return messages;
}

DateTime? clinicalTimestamp(dynamic value) {
  if (value is! String || value.trim().isEmpty) return null;
  return DateTime.tryParse(value)?.toLocal();
}

String formatClinicalDateTime(dynamic value) {
  final date = clinicalTimestamp(value);
  if (date == null) return 'Date unavailable';
  const months = [
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec'
  ];
  final hour = date.hour % 12 == 0 ? 12 : date.hour % 12;
  final minute = date.minute.toString().padLeft(2, '0');
  final period = date.hour < 12 ? 'AM' : 'PM';
  return '${date.day} ${months[date.month - 1]} ${date.year} · $hour:$minute $period';
}

dynamic foodHistoryTimestamp(Map<String, dynamic> item) =>
    item['status'] == 'eaten'
        ? item['actualEatingAt']
        : item['plannedEatingAt'];

String foodHistoryDateLabel(Map<String, dynamic> item) {
  final label = item['status'] == 'eaten' ? 'Eaten' : 'Planned';
  return '$label: ${formatClinicalDateTime(foodHistoryTimestamp(item))}';
}

String bolusUnitsLabel(Map<String, dynamic> item) {
  final units = item['administeredUnits'];
  if (units is num) return '$units U';
  final recorded = '${item['recorded'] ?? ''}'.trim();
  return recorded.isEmpty ? 'Units unavailable' : recorded;
}

int compareClinicalHistory(Map<String, dynamic> left,
    Map<String, dynamic> right, dynamic Function(Map<String, dynamic>) value) {
  final leftTime = clinicalTimestamp(value(left));
  final rightTime = clinicalTimestamp(value(right));
  if (leftTime == null) return rightTime == null ? 0 : 1;
  if (rightTime == null) return -1;
  return rightTime.compareTo(leftTime);
}

Map<String, dynamic> buildMobileBolusEntry({
  required String id,
  required String patientId,
  required String patientName,
  required double units,
  required DateTime submittedAt,
  required String localTimeLabel,
}) =>
    {
      'id': id,
      'patientSlug': patientId,
      'patient': patientName,
      'time': localTimeLabel,
      'administeredUnits': units,
      'recorded': '$units U',
      'administeredAt': submittedAt.toUtc().toIso8601String(),
    };

Map<String, dynamic> buildMobileFoodEntry({
  required String id,
  required String patientId,
  required String patientName,
  required String meal,
  required String items,
  required double carbs,
  required DateTime submittedAt,
  required String localTimeLabel,
}) {
  final eventAt = submittedAt.toUtc().toIso8601String();
  return {
    'id': id,
    'patientSlug': patientId,
    'patient': patientName,
    'time': localTimeLabel,
    'meal': meal,
    'items': items,
    'carbs': '${carbs}g',
    'impact': 'Pending CGM impact',
    'status': 'eaten',
    'plannedEatingAt': eventAt,
    'actualEatingAt': eventAt,
    'announcedCarbsG': carbs,
    'consumedCarbsG': carbs,
    'confirmAnnouncedAmount': true,
  };
}

class PatientMobileApp extends StatefulWidget {
  const PatientMobileApp({super.key});
  @override
  State<PatientMobileApp> createState() => _PatientMobileAppState();
}

class _PatientMobileAppState extends State<PatientMobileApp> {
  final api = SyncApi();
  Map<String, dynamic>? account;
  Map<String, dynamic> snapshot = {};
  Timer? poller;
  bool loading = true;
  bool showWelcome = true;
  bool createAccount = false;
  bool previewWelcome = Uri.base.queryParameters['view'] == 'welcome';
  String? error;

  @override
  void initState() {
    super.initState();
    api.onLocalChange = _applyLocal;
    _restore();
  }

  Future<void> _applyLocal() async {
    final local = await api.localSnapshot();
    if (mounted && api.currentPatientId == account?['id'])
      setState(() => snapshot = local);
  }

  Future<void> _restore() async {
    await api.restore();
    if (api.token != null && api.cachedAccount != null) {
      account = api.cachedAccount;
      snapshot = await api.localSnapshot();
      if (mounted) setState(() => loading = false);
      _startPolling();
      await refresh();
      return;
    } else if (api.token != null) {
      try {
        final data = await api.snapshot();
        account = data['account'] as Map<String, dynamic>;
        snapshot = data;
        _startPolling();
      } on ApiException catch (failure) {
        error = failure.statusCode == 401
            ? 'Your session expired. Sign in again to resume synchronization.'
            : 'Connection lost. Sign in online once to enable secure offline access.';
      }
    }
    if (mounted) setState(() => loading = false);
  }

  void _startPolling() {
    poller?.cancel();
    poller = Timer.periodic(const Duration(seconds: 4), (_) => refresh());
  }

  Future<void> refresh() async {
    try {
      await api.syncOutbox();
      final data = await api.snapshot();
      if (mounted)
        setState(() {
          account = data['account'] as Map<String, dynamic>;
          snapshot = data;
          error = null;
        });
    } on ApiException catch (failure) {
      await _applyLocal();
      if (mounted)
        setState(() => error = failure.statusCode == 401
            ? 'Your session expired. Sign in again to resume synchronization.'
            : 'Connection lost. Showing records saved securely on this device.');
    }
  }

  Future<void> signedIn(Map<String, dynamic> value) async {
    setState(() {
      account = value;
      loading = true;
    });
    await refresh();
    _startPolling();
    if (mounted) setState(() => loading = false);
  }

  Future<void> signOut() async {
    poller?.cancel();
    await api.signOut();
    if (mounted)
      setState(() {
        account = null;
        snapshot = {};
        error = null;
        showWelcome = true;
      });
  }

  @override
  void dispose() {
    poller?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'Diabetes Digital Twin',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          useMaterial3: true,
          scaffoldBackgroundColor: background,
          colorScheme: ColorScheme.fromSeed(
              seedColor: green,
              primary: green,
              secondary: dashboardCyan,
              surface: Colors.white,
              primaryContainer: dashboardIce),
          appBarTheme: const AppBarTheme(
              backgroundColor: Colors.white, foregroundColor: darkGreen),
          inputDecorationTheme: InputDecorationTheme(
              filled: true,
              fillColor: Colors.white,
              border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: const BorderSide(color: dashboardBorder)),
              enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: const BorderSide(color: dashboardBorder)),
              focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: const BorderSide(color: green, width: 1.5))),
          cardTheme: CardThemeData(
              color: Colors.white,
              elevation: 1,
              shadowColor: authNavy.withValues(alpha: 0.08),
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(16),
                  side: const BorderSide(color: dashboardBorder))),
        ),
        home: loading
            ? const Scaffold(body: Center(child: CircularProgressIndicator()))
            : previewWelcome
                ? PatientWelcome(
                    error: error,
                    onSignIn: () => setState(() {
                          previewWelcome = false;
                          showWelcome = false;
                        }),
                    onCreateAccount: () => setState(() {
                          previewWelcome = false;
                          account = null;
                          createAccount = true;
                          showWelcome = false;
                        }))
                : account == null
                    ? showWelcome
                        ? PatientWelcome(
                            error: error,
                            onSignIn: () => setState(() {
                                  createAccount = false;
                                  showWelcome = false;
                                }),
                            onCreateAccount: () => setState(() {
                                  createAccount = true;
                                  showWelcome = false;
                                }))
                        : PatientSignIn(
                            key: ValueKey(createAccount),
                            api: api,
                            initialCreating: createAccount,
                            onBack: () => setState(() => showWelcome = true),
                            onSignedIn: signedIn)
                    : PatientPortal(
                        api: api,
                        account: account!,
                        snapshot: snapshot,
                        error: error,
                        onRefresh: refresh,
                        onLocalChange: _applyLocal,
                        onAccountUpdated: (value) async {
                          if (mounted) setState(() => account = value);
                        },
                        onSignOut: signOut),
      );
}

class PatientWelcome extends StatefulWidget {
  const PatientWelcome(
      {super.key,
      required this.onSignIn,
      required this.onCreateAccount,
      this.error});
  final VoidCallback onSignIn;
  final VoidCallback onCreateAccount;
  final String? error;

  @override
  State<PatientWelcome> createState() => _PatientWelcomeState();
}

class _PatientWelcomeState extends State<PatientWelcome> {
  bool _started = false;
  bool _visible = false;
  bool _reduceMotion = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _reduceMotion = MediaQuery.disableAnimationsOf(context);
    if (_reduceMotion) {
      _started = true;
      _visible = true;
    } else if (!_started) {
      _started = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) setState(() => _visible = true);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final media = MediaQuery.of(context);
    final width = media.size.width;
    final illustrationHeight = (width * 0.72).clamp(230.0, 380.0);
    final transitionDuration =
        _reduceMotion ? Duration.zero : const Duration(milliseconds: 520);
    const features = [
      (
        icon: Icons.monitor_heart_outlined,
        title: 'See the whole picture.',
        description:
            'Bring glucose readings, meals, and insulin records together.'
      ),
      (
        icon: Icons.auto_graph_rounded,
        title: 'Glucose predictions',
        description:
            'GlucoTwin predicts glucose levels for the next 30, 60, and 120 minutes using your digital twin.'
      ),
      (
        icon: Icons.medication_outlined,
        title: 'Bolus & basal optimization',
        description:
            'Explore personalized bolus doses and basal rates by simulating different insulin options with your digital twin.'
      ),
    ];

    return Scaffold(
      backgroundColor: authNavyDeep,
      body: SafeArea(
        child: ListView(
          padding: EdgeInsets.fromLTRB(20, 18, 20, 24 + media.padding.bottom),
          children: [
            const Row(children: [
              Icon(Icons.monitor_heart_outlined,
                  color: Color(0xFF9DDFFF), size: 25),
              SizedBox(width: 9),
              Text('GlucoTwin',
                  style: TextStyle(
                      color: Colors.white,
                      fontSize: 20,
                      fontWeight: FontWeight.w700,
                      letterSpacing: -0.5)),
            ]),
            const SizedBox(height: 18),
            AnimatedOpacity(
              opacity: _visible ? 1 : 0,
              duration: transitionDuration,
              curve: Curves.easeOut,
              child: AnimatedSlide(
                offset: _visible ? Offset.zero : const Offset(0, 0.035),
                duration: transitionDuration,
                curve: Curves.easeOutCubic,
                child: SizedBox(
                  height: illustrationHeight,
                  child: Image.asset(
                    'assets/images/onboarding-digital-twin.png',
                    fit: BoxFit.contain,
                    semanticLabel:
                        'A person connected to an anatomical digital twin and AI model',
                  ),
                ),
              ),
            ),
            const SizedBox(height: 10),
            AnimatedOpacity(
              opacity: _visible ? 1 : 0,
              duration: transitionDuration,
              curve: Curves.easeOut,
              child: AnimatedSlide(
                offset: _visible ? Offset.zero : const Offset(0, 0.025),
                duration: transitionDuration,
                curve: Curves.easeOutCubic,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text.rich(
                      const TextSpan(children: [
                        TextSpan(text: 'Gluco'),
                        TextSpan(
                            text: 'Twin',
                            style: TextStyle(color: Color(0xFF8ED7F7))),
                      ]),
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: (width * 0.135).clamp(44.0, 64.0),
                        height: 1,
                        fontWeight: FontWeight.w700,
                        letterSpacing: -2.5,
                      ),
                    ),
                    const SizedBox(height: 18),
                    const Text(
                      'Meet the digital twin that brings your glucose, daily habits, and care team together—so every day feels a little easier to understand.',
                      style: TextStyle(
                          color: Color(0xFFBBD0E0), fontSize: 15, height: 1.65),
                    ),
                    const SizedBox(height: 24),
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton(
                        onPressed: widget.onSignIn,
                        style: FilledButton.styleFrom(
                          backgroundColor: const Color(0xFF97D8F4),
                          foregroundColor: const Color(0xFF082C49),
                          padding: const EdgeInsets.symmetric(vertical: 15),
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(10)),
                        ),
                        child: const Text('Sign in',
                            style: TextStyle(fontWeight: FontWeight.w700)),
                      ),
                    ),
                    const SizedBox(height: 10),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton(
                        onPressed: widget.onCreateAccount,
                        style: OutlinedButton.styleFrom(
                          foregroundColor: Colors.white,
                          side: const BorderSide(color: Color(0x668FD8FF)),
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(10)),
                        ),
                        child: const Text('New patient? Create account',
                            style: TextStyle(fontWeight: FontWeight.w600)),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 42),
            const Text('ONE PLACE. A FULLER PICTURE.',
                style: TextStyle(
                    color: Color(0xFF91C7E6),
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.8)),
            const SizedBox(height: 14),
            ...features.map((feature) => Padding(
                  padding: const EdgeInsets.only(bottom: 14),
                  child: _OnboardingFeatureCard(
                    icon: feature.icon,
                    title: feature.title,
                    description: feature.description,
                  ),
                )),
            if (widget.error != null)
              Container(
                margin: const EdgeInsets.only(top: 8),
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                    color: const Color(0xFF3D2432),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: const Color(0xFF9B4C64))),
                child: Text(widget.error!,
                    style: const TextStyle(color: Color(0xFFFFD9E2))),
              ),
          ],
        ),
      ),
    );
  }
}

class _OnboardingFeatureCard extends StatelessWidget {
  const _OnboardingFeatureCard(
      {required this.icon, required this.title, required this.description});

  final IconData icon;
  final String title;
  final String description;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
              colors: [Color(0xFF153B59), Color(0xFF0C2A44)],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: const Color(0x2691C6E2)),
        ),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Container(
            width: 42,
            height: 42,
            alignment: Alignment.center,
            decoration: BoxDecoration(
                color: const Color(0x1A8ED7F7),
                borderRadius: BorderRadius.circular(12)),
            child: Icon(icon, color: const Color(0xFF9BD5F3), size: 23),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title,
                    style: const TextStyle(
                        color: Colors.white,
                        fontSize: 17,
                        fontWeight: FontWeight.w700)),
                const SizedBox(height: 7),
                Text(description,
                    style: const TextStyle(
                        color: Color(0xFFAAC1D3), fontSize: 13, height: 1.55)),
              ],
            ),
          ),
        ]),
      );
}

ThemeData _authScreenTheme(BuildContext context) {
  final base = Theme.of(context);
  final border = OutlineInputBorder(
    borderRadius: BorderRadius.circular(10),
    borderSide: const BorderSide(color: authBorder),
  );
  return base.copyWith(
    scaffoldBackgroundColor: Colors.white,
    colorScheme: base.colorScheme.copyWith(
      primary: authBlue,
      primaryContainer: authIce,
      onPrimary: Colors.white,
      surface: Colors.white,
      outline: authBorder,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Colors.white,
      border: border,
      enabledBorder: border,
      focusedBorder: border.copyWith(
          borderSide: const BorderSide(color: authBlue, width: 1.8)),
      errorBorder: border.copyWith(
          borderSide: const BorderSide(color: Color(0xFFB42318))),
      focusedErrorBorder: border.copyWith(
          borderSide: const BorderSide(color: Color(0xFFB42318), width: 1.8)),
      labelStyle: const TextStyle(color: Color(0xFF526A7C)),
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 15),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: authBlue,
        foregroundColor: Colors.white,
        disabledBackgroundColor: authBlue.withValues(alpha: 0.45),
        minimumSize: const Size.fromHeight(50),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        textStyle: const TextStyle(fontWeight: FontWeight.w700),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(foregroundColor: authBlue),
    ),
    cardTheme: CardThemeData(
      color: Colors.white,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: const BorderSide(color: authBorder),
      ),
    ),
  );
}

class PatientSignIn extends StatefulWidget {
  const PatientSignIn(
      {super.key,
      required this.api,
      required this.initialCreating,
      required this.onBack,
      required this.onSignedIn});
  final SyncApi api;
  final bool initialCreating;
  final VoidCallback onBack;
  final Future<void> Function(Map<String, dynamic>) onSignedIn;
  @override
  State<PatientSignIn> createState() => _PatientSignInState();
}

class _PatientSignInState extends State<PatientSignIn> {
  final key = GlobalKey<FormState>();
  final email = TextEditingController();
  final password = TextEditingController();
  final name = TextEditingController();
  final age = TextEditingController();
  final weight = TextEditingController();
  final height = TextEditingController();
  bool creating = false;
  bool busy = false;
  String? error;
  String? doctorId;
  List<dynamic> doctors = [];

  @override
  void initState() {
    super.initState();
    creating = widget.initialCreating;
    _loadDoctors();
  }

  Future<void> _loadDoctors() async {
    try {
      final value = await widget.api.doctors();
      value.sort((a, b) => doctorRank(b as Map<String, dynamic>)
          .compareTo(doctorRank(a as Map<String, dynamic>)));
      if (mounted) setState(() => doctors = value);
    } catch (_) {
      if (mounted)
        setState(() => error = 'Connect to the sync service to see doctors.');
    }
  }

  Future<void> _submit() async {
    if (!key.currentState!.validate()) return;
    if (creating && doctorId == null) {
      setState(() => error = 'Choose a doctor.');
      return;
    }
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final result = creating
          ? await widget.api.register({
              'id': DateTime.now().microsecondsSinceEpoch.toRadixString(36),
              'role': 'patient',
              'email': email.text.trim().toLowerCase(),
              'password': password.text,
              'patientProfile': {
                'fullName': name.text.trim(),
                'age': age.text,
                'weight': weight.text,
                'height': height.text,
                'diabetesType': '',
                'insulinPlan': '',
                'medications': '',
                'allergies': '',
                'emergencyContact': '',
                'selectedDoctorId': doctorId
              },
            })
          : await widget.api.login(email.text.trim(), password.text);
      await widget.onSignedIn(result);
    } catch (e) {
      if (mounted)
        setState(() => error = e.toString().replaceFirst('Exception: ', ''));
    }
    if (mounted) setState(() => busy = false);
  }

  @override
  void dispose() {
    for (final controller in [email, password, name, age, weight, height]) {
      controller.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final media = MediaQuery.of(context);
    final compactHeader = media.size.height < 700;

    return Theme(
      data: _authScreenTheme(context),
      child: Scaffold(
        resizeToAvoidBottomInset: true,
        body: SafeArea(
          child: SingleChildScrollView(
            keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Container(
                  color: authNavy,
                  padding:
                      EdgeInsets.fromLTRB(12, 8, 20, compactHeader ? 22 : 28),
                  child: Column(children: [
                    Align(
                      alignment: Alignment.centerLeft,
                      child: IconButton(
                        tooltip: 'Back to welcome',
                        onPressed: widget.onBack,
                        color: Colors.white,
                        icon: const Icon(Icons.arrow_back),
                      ),
                    ),
                    Image.asset(
                      'assets/images/auth-cgm-virtual-patient.png',
                      height: compactHeader ? 118 : 160,
                      width: double.infinity,
                      fit: BoxFit.contain,
                      semanticLabel:
                          'CGM sensor data flowing into a virtual patient digital twin',
                    ),
                    const SizedBox(height: 12),
                    const Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(Icons.monitor_heart_outlined,
                            color: Color(0xFF9DDFFF), size: 23),
                        SizedBox(width: 8),
                        Text('Diabetes Digital Twin',
                            style: TextStyle(
                                color: Colors.white,
                                fontSize: 18,
                                fontWeight: FontWeight.w700)),
                      ],
                    ),
                  ]),
                ),
                Center(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 480),
                    child: Padding(
                      padding: EdgeInsets.fromLTRB(
                          24, 28, 24, 28 + media.padding.bottom),
                      child: Form(
                        key: key,
                        child: FocusTraversalGroup(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Text(
                                creating ? 'Join as a patient' : 'Welcome back',
                                style: const TextStyle(
                                  color: Color(0xFF172033),
                                  fontSize: 27,
                                  fontWeight: FontWeight.w800,
                                  letterSpacing: -0.6,
                                ),
                              ),
                              const SizedBox(height: 6),
                              Text(
                                creating
                                    ? 'Complete your health information and choose a doctor.'
                                    : 'Sign in to continue to your dashboard.',
                                style: const TextStyle(
                                    color: Color(0xFF667085), height: 1.45),
                              ),
                              if (!creating) ...[
                                const SizedBox(height: 22),
                                const Text('Saved account',
                                    style: TextStyle(
                                        fontWeight: FontWeight.w700,
                                        color: Color(0xFF172033))),
                                const SizedBox(height: 8),
                                Material(
                                  color: Colors.white,
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(10),
                                    side: const BorderSide(color: authBorder),
                                  ),
                                  child: ListTile(
                                    shape: RoundedRectangleBorder(
                                        borderRadius:
                                            BorderRadius.circular(10)),
                                    leading: const CircleAvatar(
                                      backgroundColor: authIce,
                                      child: Text('OH',
                                          style: TextStyle(
                                              color: authBlue,
                                              fontWeight: FontWeight.w700)),
                                    ),
                                    title: const Text('Omar Hassan'),
                                    subtitle:
                                        const Text('omar.hassan@example.com'),
                                    onTap: busy
                                        ? null
                                        : () {
                                            email.text =
                                                'omar.hassan@example.com';
                                            password.text = 'password';
                                            setState(() => error = null);
                                          },
                                  ),
                                ),
                              ],
                              const SizedBox(height: 24),
                              if (creating) ...[
                                TextFormField(
                                    controller: name,
                                    textInputAction: TextInputAction.next,
                                    decoration: const InputDecoration(
                                        labelText: 'Full name'),
                                    validator: (v) =>
                                        v == null || v.trim().isEmpty
                                            ? 'Enter your name'
                                            : null),
                                const SizedBox(height: 12),
                                LayoutBuilder(builder: (context, constraints) {
                                  final stackFields =
                                      constraints.maxWidth < 340 ||
                                          media.textScaler.scale(1) > 1.25;
                                  final ageField = TextFormField(
                                      controller: age,
                                      keyboardType: TextInputType.number,
                                      textInputAction: TextInputAction.next,
                                      decoration: const InputDecoration(
                                          labelText: 'Age'),
                                      validator: (v) =>
                                          (int.tryParse(v ?? '') ?? 0) < 1
                                              ? 'Enter age'
                                              : null);
                                  final weightField = TextFormField(
                                      controller: weight,
                                      keyboardType: TextInputType.number,
                                      textInputAction: TextInputAction.next,
                                      decoration: const InputDecoration(
                                          labelText: 'Weight kg'),
                                      validator: (v) =>
                                          (double.tryParse(v ?? '') ?? 0) <= 0
                                              ? 'Enter weight'
                                              : null);
                                  if (stackFields) {
                                    return Column(children: [
                                      ageField,
                                      const SizedBox(height: 12),
                                      weightField,
                                    ]);
                                  }
                                  return Row(children: [
                                    Expanded(child: ageField),
                                    const SizedBox(width: 12),
                                    Expanded(child: weightField),
                                  ]);
                                }),
                                const SizedBox(height: 12),
                                TextFormField(
                                    controller: height,
                                    keyboardType: TextInputType.number,
                                    textInputAction: TextInputAction.next,
                                    decoration: const InputDecoration(
                                        labelText: 'Height cm'),
                                    validator: (v) =>
                                        (double.tryParse(v ?? '') ?? 0) <= 0
                                            ? 'Enter height'
                                            : null),
                                const SizedBox(height: 28),
                                const Text('Choose your doctor',
                                    style: TextStyle(
                                        color: Color(0xFF172033),
                                        fontWeight: FontWeight.w700)),
                                const SizedBox(height: 8),
                                ...doctors.asMap().entries.map((entry) {
                                  final doctor =
                                      entry.value as Map<String, dynamic>;
                                  final profile = doctor['doctorProfile']
                                          as Map<String, dynamic>? ??
                                      {};
                                  final rating = doctor['rating']
                                          as Map<String, dynamic>? ??
                                      {};
                                  final selected = doctorId == doctor['id'];
                                  return Card(
                                      child: InkWell(
                                          onTap: () => setState(() => doctorId =
                                              doctor['id'] as String),
                                          child: Padding(
                                              padding: const EdgeInsets.all(12),
                                              child: Column(
                                                  crossAxisAlignment:
                                                      CrossAxisAlignment.start,
                                                  children: [
                                                    Row(children: [
                                                      Icon(
                                                          selected
                                                              ? Icons
                                                                  .radio_button_checked
                                                              : Icons
                                                                  .radio_button_off,
                                                          color: authBlue),
                                                      const SizedBox(width: 10),
                                                      Expanded(
                                                          child: Text(
                                                              '#${entry.key + 1}  ${profile['fullName'] ?? 'Doctor'}',
                                                              style: const TextStyle(
                                                                  fontWeight:
                                                                      FontWeight
                                                                          .w700)))
                                                    ]),
                                                    Padding(
                                                        padding:
                                                            const EdgeInsets
                                                                .only(
                                                                left: 34,
                                                                top: 4),
                                                        child: Text(
                                                            '${profile['specialty'] ?? ''} · ${profile['yearsExperience'] ?? '0'} years experience',
                                                            style:
                                                                const TextStyle(
                                                                    color:
                                                                        muted))),
                                                    Padding(
                                                        padding:
                                                            const EdgeInsets
                                                                .only(
                                                                left: 34,
                                                                top: 4),
                                                        child: Text(
                                                            rating['average'] ==
                                                                    null
                                                                ? 'No ratings yet'
                                                                : '${(rating['average'] as num).toStringAsFixed(1)} / 5 · ${rating['count']} ratings${rating['sample'] == true ? ' (sample)' : ''}',
                                                            style: const TextStyle(
                                                                color:
                                                                    authBlueDark,
                                                                fontSize: 13))),
                                                    if (profile['medicalSchool'] !=
                                                        null)
                                                      Padding(
                                                          padding:
                                                              const EdgeInsets
                                                                  .fromLTRB(
                                                                  16, 0, 16, 8),
                                                          child: Text(
                                                              '${profile['medicalSchool']}',
                                                              style:
                                                                  const TextStyle(
                                                                      color:
                                                                          muted,
                                                                      fontSize:
                                                                          13))),
                                                    if ('${profile['qualifications'] ?? ''}'
                                                        .isNotEmpty)
                                                      Padding(
                                                          padding:
                                                              const EdgeInsets
                                                                  .fromLTRB(
                                                                  16, 0, 16, 8),
                                                          child: Text(
                                                              'Qualifications: ${profile['qualifications']}',
                                                              style:
                                                                  const TextStyle(
                                                                      fontSize:
                                                                          13))),
                                                    if (profile['certificates']
                                                            is List &&
                                                        (profile['certificates']
                                                                as List)
                                                            .isNotEmpty)
                                                      Padding(
                                                          padding:
                                                              const EdgeInsets
                                                                  .fromLTRB(
                                                                  16, 0, 16, 8),
                                                          child: Text(
                                                              'Certificates: ${(profile['certificates'] as List).join(', ')}',
                                                              style:
                                                                  const TextStyle(
                                                                      fontSize:
                                                                          13))),
                                                    if (profile['papers']
                                                            is List &&
                                                        (profile['papers']
                                                                as List)
                                                            .isNotEmpty)
                                                      Padding(
                                                          padding:
                                                              const EdgeInsets
                                                                  .fromLTRB(
                                                                  16, 0, 16, 8),
                                                          child: Text(
                                                              'Papers: ${(profile['papers'] as List).join(', ')}',
                                                              style:
                                                                  const TextStyle(
                                                                      fontSize:
                                                                          13))),
                                                    if (profile['bio'] != null)
                                                      Padding(
                                                          padding:
                                                              const EdgeInsets
                                                                  .fromLTRB(16,
                                                                  0, 16, 12),
                                                          child: Text(
                                                              '${profile['bio']}',
                                                              style:
                                                                  const TextStyle(
                                                                      fontSize:
                                                                          13))),
                                                  ]))));
                                }),
                              ],
                              TextFormField(
                                  controller: email,
                                  keyboardType: TextInputType.emailAddress,
                                  textInputAction: TextInputAction.next,
                                  autofillHints: const [AutofillHints.email],
                                  decoration:
                                      const InputDecoration(labelText: 'Email'),
                                  validator: (v) =>
                                      v == null || !v.contains('@')
                                          ? 'Enter a valid email'
                                          : null),
                              const SizedBox(height: 12),
                              TextFormField(
                                  controller: password,
                                  obscureText: true,
                                  textInputAction: TextInputAction.done,
                                  onFieldSubmitted:
                                      busy ? null : (_) => _submit(),
                                  autofillHints: [
                                    creating
                                        ? AutofillHints.newPassword
                                        : AutofillHints.password
                                  ],
                                  decoration: const InputDecoration(
                                      labelText: 'Password'),
                                  validator: (v) =>
                                      v == null || v.length < (creating ? 8 : 1)
                                          ? 'Enter your password'
                                          : null),
                              if (error != null)
                                Container(
                                  margin: const EdgeInsets.only(top: 14),
                                  padding: const EdgeInsets.all(12),
                                  decoration: BoxDecoration(
                                    color: const Color(0xFFFFF1F3),
                                    borderRadius: BorderRadius.circular(9),
                                    border: Border.all(
                                        color: const Color(0xFFFECACA)),
                                  ),
                                  child: Text(error!,
                                      style: const TextStyle(
                                          color: Color(0xFFB42318))),
                                ),
                              const SizedBox(height: 20),
                              FilledButton(
                                  onPressed: busy ? null : _submit,
                                  child: Text(busy
                                      ? 'Please wait...'
                                      : creating
                                          ? 'Create account'
                                          : 'Sign in')),
                              const SizedBox(height: 4),
                              TextButton(
                                  onPressed: busy
                                      ? null
                                      : () => setState(() {
                                            creating = !creating;
                                            error = null;
                                          }),
                                  child: Text(creating
                                      ? 'Already have an account? Sign in'
                                      : 'New patient? Create account')),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class PatientPortal extends StatefulWidget {
  const PatientPortal(
      {super.key,
      required this.api,
      required this.account,
      required this.snapshot,
      required this.error,
      required this.onRefresh,
      required this.onLocalChange,
      required this.onAccountUpdated,
      required this.onSignOut});
  final SyncApi api;
  final Map<String, dynamic> account;
  final Map<String, dynamic> snapshot;
  final String? error;
  final Future<void> Function() onRefresh;
  final Future<void> Function() onLocalChange;
  final Future<void> Function(Map<String, dynamic>) onAccountUpdated;
  final Future<void> Function() onSignOut;
  @override
  State<PatientPortal> createState() => _PatientPortalState();
}

class _PatientPortalState extends State<PatientPortal>
    with WidgetsBindingObserver {
  int tab = 0;
  final pageScroll = ScrollController();
  bool nearMessageBottom = true;
  List<Map<String, dynamic>> contacts = [];
  bool contactsLoading = false;
  bool contactsSaving = false;
  String? contactsError;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    tab = switch (Uri.base.queryParameters['view']) {
      'record' => 1,
      'care' => 2,
      'profile' => 3,
      _ => 0
    };
    pageScroll.addListener(_trackMessageScroll);
    _loadContacts();
    if (tab == 2) _scrollToLatest(force: true);
  }

  String? actionError;
  final draft = TextEditingController();
  List<dynamic> list(String key) =>
      widget.snapshot[key] as List<dynamic>? ?? [];
  Map<String, dynamic> get profile =>
      widget.account['patientProfile'] as Map<String, dynamic>? ?? {};
  String get patientId => widget.account['id'] as String;
  Map<String, dynamic>? get assignment {
    for (final raw in list('assignments')) {
      final item = raw as Map<String, dynamic>;
      if (item['patientId'] == patientId &&
          item['doctorId'] == profile['selectedDoctorId']) return item;
    }
    return null;
  }

  Map<String, dynamic>? get doctor {
    for (final raw in list('doctors')) {
      final item = raw as Map<String, dynamic>;
      if (item['id'] == profile['selectedDoctorId']) return item;
    }
    return null;
  }

  Future<void> add(String kind, Map<String, dynamic> item) async {
    try {
      if (const {'glucose', 'food', 'bolus'}.contains(kind)) {
        await widget.api.queueAdd(kind, item);
        await widget.onLocalChange();
        if (mounted)
          setState(() => actionError =
              'Saved on this device; synchronization will continue automatically.');
      } else {
        await widget.api.add(kind, item);
        await widget.onRefresh();
        if (mounted) setState(() => actionError = null);
      }
    } catch (e) {
      if (mounted)
        setState(
            () => actionError = e.toString().replaceFirst('Exception: ', ''));
      rethrow;
    }
  }

  void _trackMessageScroll() {
    if (!pageScroll.hasClients || tab != 2) return;
    nearMessageBottom =
        pageScroll.position.maxScrollExtent - pageScroll.offset <= 96;
  }

  void _scrollToLatest({bool force = false}) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !pageScroll.hasClients || tab != 2) return;
      if (!force && !nearMessageBottom) return;
      pageScroll.animateTo(pageScroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 180), curve: Curves.easeOut);
      nearMessageBottom = true;
    });
  }

  String _newestMessageKey(dynamic rows) {
    final ordered = chronologicalConversationMessages(rows);
    if (ordered.isEmpty) return '';
    final newest = ordered.last;
    return '${ordered.length}:${newest['id']}:${newest['sentAt']}';
  }

  @override
  void didUpdateWidget(covariant PatientPortal oldWidget) {
    super.didUpdateWidget(oldWidget);
    final changed = _newestMessageKey(oldWidget.snapshot['messages']) !=
        _newestMessageKey(widget.snapshot['messages']);
    if (changed) _scrollToLatest();
  }

  Future<void> _loadContacts() async {
    if (contactsLoading) return;
    if (mounted) setState(() => contactsLoading = true);
    try {
      final value = await widget.api.emergencyContacts();
      if (mounted)
        setState(() {
          contacts = value;
          contactsError = null;
        });
    } catch (error) {
      if (mounted)
        setState(() =>
            contactsError = error.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => contactsLoading = false);
    }
  }

  Future<void> _refreshAll() async {
    await widget.onRefresh();
    if (tab == 3) await _loadContacts();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      widget.onRefresh();
      _loadContacts();
    }
  }

  String get nowLabel => TimeOfDay.now().format(context);
  String get nextId => DateTime.now().microsecondsSinceEpoch.toRadixString(36);
  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    pageScroll.removeListener(_trackMessageScroll);
    pageScroll.dispose();
    draft.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final titles = ['Overview', 'Record', 'Care team', 'Profile'];
    return Scaffold(
      appBar: AppBar(title: Text(titles[tab]), actions: [
        IconButton(
            tooltip: 'Refresh',
            onPressed: _refreshAll,
            icon: const Icon(Icons.refresh))
      ]),
      body: RefreshIndicator(
          onRefresh: _refreshAll,
          child: ListView(
              controller: pageScroll,
              padding: const EdgeInsets.all(16),
              children: [
                if (widget.error != null) _notice(widget.error!),
                if (actionError != null) _notice(actionError!),
                AnimatedSwitcher(
                    duration: MediaQuery.disableAnimationsOf(context)
                        ? Duration.zero
                        : const Duration(milliseconds: 180),
                    child: KeyedSubtree(
                        key: ValueKey(tab),
                        child: switch (tab) {
                          0 => _overview(),
                          1 => _records(),
                          2 => _care(),
                          _ => _profile(),
                        }))
              ])),
      bottomNavigationBar: NavigationBar(
          selectedIndex: tab,
          onDestinationSelected: (value) {
            setState(() => tab = value);
            if (value == 2) _scrollToLatest(force: true);
            if (value == 3) _loadContacts();
          },
          destinations: const [
            NavigationDestination(
                icon: Icon(Icons.space_dashboard_outlined), label: 'Overview'),
            NavigationDestination(
                icon: Icon(Icons.add_chart_outlined), label: 'Record'),
            NavigationDestination(
                icon: Icon(Icons.forum_outlined), label: 'Care'),
            NavigationDestination(
                icon: Icon(Icons.person_outline), label: 'Profile'),
          ]),
    );
  }

  Widget _notice(String message) => Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: DecoratedBox(
          decoration: BoxDecoration(
              color: const Color(0xFFFFF7ED),
              borderRadius: BorderRadius.circular(6)),
          child: Padding(
              padding: const EdgeInsets.all(12), child: Text(message))));
  Widget _panel(String title, Widget child, {Widget? action}) => Card(
      child: Padding(
          padding: const EdgeInsets.all(16),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Expanded(
                  child: Text(title,
                      style: const TextStyle(
                          fontSize: 17,
                          fontWeight: FontWeight.bold,
                          color: darkGreen))),
              if (action != null) action,
            ]),
            const SizedBox(height: 12),
            child
          ])));
  Widget _empty(String text) =>
      Text(text, style: const TextStyle(color: muted));

  Widget _overview() {
    final food = list('food')
        .map((item) => Map<String, dynamic>.from(item as Map))
        .toList()
      ..sort((a, b) => compareClinicalHistory(a, b, foodHistoryTimestamp));
    final bolus = list('bolus')
        .map((item) => Map<String, dynamic>.from(item as Map))
        .toList()
      ..sort((a, b) =>
          compareClinicalHistory(a, b, (item) => item['administeredAt']));
    final demo = widget.snapshot['demo'] as Map<String, dynamic>?;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Text('Hello, ${profile['fullName'] ?? 'Patient'}',
          style: const TextStyle(
              fontSize: 24, fontWeight: FontWeight.bold, color: darkGreen)),
      const SizedBox(height: 4),
      const Text('Your readings and care records',
          style: TextStyle(color: muted)),
      const SizedBox(height: 16),
      if (demo != null) ..._demoDashboard(demo),
      FilledButton.icon(
          onPressed: () => setState(() => tab = 1),
          icon: const Icon(Icons.add),
          label: const Text('Record food or insulin')),
      const SizedBox(height: 8),
      _panel(
          'Recorded totals',
          Column(children: [
            _countRow(
                Icons.restaurant_outlined, 'Food entries', list('food').length),
            _countRow(
                Icons.vaccines_outlined, 'Bolus logs', list('bolus').length),
          ])),
      _panel(
          'Care status',
          Text(assignment?['status'] == 'accepted'
              ? 'Connected to ${doctor?['doctorProfile']?['fullName'] ?? 'your doctor'}'
              : 'Doctor request ${assignment?['status'] ?? 'pending'}')),
      _panel(
          'Recent food',
          food.isEmpty
              ? _empty('No food entries yet.')
              : Column(
                  children: food
                      .take(3)
                      .map((item) => ListTile(
                          contentPadding: EdgeInsets.zero,
                          leading: const Icon(Icons.restaurant_outlined,
                              color: green),
                          title: Text('${item['meal']}: ${item['items']}'),
                          subtitle: Text(
                              '${item['carbs']} carbs\n${foodHistoryDateLabel(item)}')))
                      .toList())),
      _panel(
          'Manual bolus log',
          bolus.isEmpty
              ? _empty('No bolus logs yet.')
              : Column(
                  children: bolus
                      .take(3)
                      .map((item) => ListTile(
                          contentPadding: EdgeInsets.zero,
                          leading:
                              const Icon(Icons.vaccines_outlined, color: green),
                          title: Text(bolusUnitsLabel(item)),
                          subtitle: Text(
                              formatClinicalDateTime(item['administeredAt']))))
                      .toList())),
      if (demo == null) ...[
        _panel('CGM and digital twin',
            _empty('No connected CGM or validated forecast is available yet.')),
        _notice(
            'No live CGM or validated prediction feed is connected. Predictions will appear when a supported feed is available.'),
      ],
    ]);
  }

  List<Widget> _demoDashboard(Map<String, dynamic> demo) {
    final summary = demo['summary'] as Map<String, dynamic>;
    final cgm = (demo['cgm'] as List).cast<Map<String, dynamic>>();
    final forecast = (demo['forecast'] as List).cast<Map<String, dynamic>>();
    return [
      _notice(
          'Demo patient: sample CGM readings, forecasts, and historical logs. This is not a live sensor feed.'),
      _panel(
          'Current glucose',
          Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
            Text('${summary['currentGlucose']}',
                style: const TextStyle(
                    fontSize: 42,
                    fontWeight: FontWeight.w800,
                    color: darkGreen)),
            const Padding(
                padding: EdgeInsets.only(left: 6, bottom: 8),
                child: Text('mg/dL')),
            const Spacer(),
            Text('${summary['trend']}',
                style:
                    const TextStyle(color: green, fontWeight: FontWeight.w600))
          ])),
      _panel(
          'Glucose summary',
          Column(children: [
            _detail('Time in range', '${summary['timeInRange']}%'),
            _detail('Average glucose', '${summary['averageGlucose']} mg/dL'),
            _detail('Last CGM reading', '${summary['lastReading']}')
          ])),
      const BolusRecommendationCard(),
      _panel('CGM graph', _sampleChart(cgm, forecast: false)),
      _panel(
          'Predicted glucose · demo',
          Column(
              children: (demo['forecastSnapshots'] as List).map((raw) {
            final item = raw as Map<String, dynamic>;
            return _detail('After ${item['horizon']}',
                '${item['glucose']} mg/dL · ${item['trend']}');
          }).toList())),
      _panel(
          'Digital twin forecast · demo',
          Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            _sampleChart(forecast, forecast: true),
            const SizedBox(height: 8),
            const Text('Blue: sample history. Amber: simulated forecast.',
                style: TextStyle(fontSize: 12, color: muted))
          ])),
    ];
  }

  Widget _sampleChart(List<Map<String, dynamic>> rows,
      {required bool forecast}) {
    List<FlSpot> points(String key) => rows
        .asMap()
        .entries
        .where((entry) => entry.value[key] is num)
        .map((entry) =>
            FlSpot(entry.key.toDouble(), (entry.value[key] as num).toDouble()))
        .toList();
    return SizedBox(
        height: 215,
        child: Padding(
            padding: const EdgeInsets.only(top: 8, right: 12),
            child: LineChart(LineChartData(
              minY: 80,
              maxY: 260,
              minX: 0,
              maxX: (rows.length - 1).toDouble(),
              gridData: const FlGridData(
                  show: true, drawVerticalLine: false, horizontalInterval: 60),
              borderData: FlBorderData(show: false),
              titlesData: FlTitlesData(
                topTitles:
                    const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                rightTitles:
                    const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                leftTitles: AxisTitles(
                    sideTitles: SideTitles(
                        showTitles: true,
                        reservedSize: 32,
                        interval: 60,
                        getTitlesWidget: (value, meta) => Text(
                            '${value.toInt()}',
                            style:
                                const TextStyle(fontSize: 10, color: muted)))),
                bottomTitles: AxisTitles(
                    sideTitles: SideTitles(
                        showTitles: true,
                        reservedSize: 26,
                        interval: forecast ? 3 : 6,
                        getTitlesWidget: (value, meta) {
                          final index = value.toInt();
                          if (index < 0 || index >= rows.length)
                            return const SizedBox.shrink();
                          return Padding(
                              padding: const EdgeInsets.only(top: 7),
                              child: Text('${rows[index]['time']}',
                                  style: const TextStyle(
                                      fontSize: 10, color: muted)));
                        })),
              ),
              lineBarsData: [
                LineChartBarData(
                    spots: points(forecast ? 'historical' : 'glucose'),
                    color: green,
                    barWidth: 2.5,
                    dotData: const FlDotData(show: false),
                    belowBarData: BarAreaData(
                        show: !forecast, color: green.withValues(alpha: 0.08))),
                if (forecast)
                  LineChartBarData(
                      spots: [
                        FlSpot(7, (rows[7]['historical'] as num).toDouble()),
                        ...points('predicted')
                      ],
                      color: const Color(0xFFC68A19),
                      dashArray: [5, 4],
                      barWidth: 2.5,
                      dotData: const FlDotData(show: false)),
              ],
            ))));
  }

  Widget _countRow(IconData icon, String label, int count) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 7),
      child: Row(children: [
        Icon(icon, color: green, size: 20),
        const SizedBox(width: 9),
        Expanded(child: Text(label)),
        Text('$count', style: const TextStyle(fontWeight: FontWeight.bold))
      ]));

  Widget _syncStatus(Map<String, dynamic> item) {
    final state = item['syncState'] ?? 'synced';
    final (label, color) = switch (state) {
      'pending' => (
          'Saved on this device; waiting to sync',
          const Color(0xFF9A6700)
        ),
      'syncing' => ('Syncing', const Color(0xFF175CD3)),
      'conflict' || 'failed' => ('Needs attention', Colors.red),
      _ => ('Synced', green),
    };
    return Row(children: [
      Icon(
          state == 'synced'
              ? Icons.cloud_done_outlined
              : state == 'syncing'
                  ? Icons.sync
                  : state == 'pending'
                      ? Icons.cloud_upload_outlined
                      : Icons.error_outline,
          size: 15,
          color: color),
      const SizedBox(width: 5),
      Expanded(
          child: Text(label, style: TextStyle(fontSize: 12, color: color))),
      if (state == 'conflict' || state == 'failed')
        TextButton(
            onPressed: () => widget.api.retry('${item['syncOperationId']}'),
            child: const Text('Retry'))
    ]);
  }

  Widget _records() {
    final food = list('food')
        .map((item) => Map<String, dynamic>.from(item as Map))
        .toList()
      ..sort((a, b) => compareClinicalHistory(a, b, foodHistoryTimestamp));
    final bolus = list('bolus')
        .map((item) => Map<String, dynamic>.from(item as Map))
        .toList()
      ..sort((a, b) =>
          compareClinicalHistory(a, b, (item) => item['administeredAt']));
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      _panel(
          'Food',
          Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            FilledButton.icon(
                onPressed: () => _entryDialog('food'),
                icon: const Icon(Icons.add),
                label: const Text('Add food')),
            const SizedBox(height: 8),
            ...food.take(5).map((item) {
              return ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text('${item['meal']}: ${item['items']}'),
                  subtitle: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('${item['carbs']} carbs · ${item['status']}'),
                        Text(foodHistoryDateLabel(item),
                            style: const TextStyle(color: muted)),
                        _syncStatus(item),
                        if (item['status'] == 'planned')
                          Wrap(spacing: 8, children: [
                            TextButton(
                                onPressed: () => _updateMeal(item, 'eaten'),
                                child: const Text('Mark eaten')),
                            TextButton(
                                onPressed: () => _updateMeal(item, 'cancelled'),
                                child: const Text('Cancel'))
                          ])
                      ]));
            }),
            if (food.isEmpty) _empty('No food entries yet.')
          ])),
      _panel(
          'Manual bolus',
          Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            FilledButton.icon(
                onPressed: () => _entryDialog('bolus'),
                icon: const Icon(Icons.add),
                label: const Text('Log bolus')),
            const SizedBox(height: 8),
            ...bolus.take(5).map((item) {
              return ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(bolusUnitsLabel(item)),
                  subtitle: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(formatClinicalDateTime(item['administeredAt']),
                            style: const TextStyle(color: muted)),
                        _syncStatus(item)
                      ]));
            }),
            if (bolus.isEmpty) _empty('No bolus logs yet.')
          ])),
    ]);
  }

  Future<void> _entryDialog(String kind) async {
    await showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (dialogContext) => _ClinicalEntryDialog(
            kind: kind,
            patientId: patientId,
            patientName: '${profile['fullName'] ?? ''}',
            onSave: (item) async {
              await add(kind, item);
            }));
  }

  Future<void> _updateMeal(Map<String, dynamic> item, String status) async {
    try {
      final eventAt = DateTime.now().toUtc().toIso8601String();
      double? actualCarbs;
      if (status == 'eaten') {
        actualCarbs = await showDialog<double>(
            context: context,
            builder: (context) => _ConsumedCarbsDialog(
                initial: double.tryParse(RegExp(r'\d+(?:\.\d+)?')
                        .firstMatch('${item['carbs']}')
                        ?.group(0) ??
                    '')));
        if (actualCarbs == null) return;
      }
      await widget.api.queueMealUpdate('${item['id']}', {
        'expectedVersion': item['version'],
        'mutationId':
            '${DateTime.now().microsecondsSinceEpoch}-${item['id']}-$status',
        'status': status,
        if (status == 'eaten') ...{
          'actualEatingAt': eventAt,
          'consumedCarbsG': actualCarbs
        },
      });
      await widget.onLocalChange();
      if (mounted)
        setState(() => actionError =
            'Meal update saved on this device; synchronization will continue automatically.');
    } catch (error) {
      if (mounted)
        setState(() =>
            actionError = error.toString().replaceFirst('Exception: ', ''));
    }
  }

  Future<void> _requestDoctor() async {
    final doctors = list('doctors').cast<Map<String, dynamic>>()
      ..sort((a, b) => doctorRank(b).compareTo(doctorRank(a)));
    final selected = await showModalBottomSheet<String>(
        context: context,
        isScrollControlled: true,
        builder: (sheetContext) => SafeArea(
                child: SizedBox(
              height: MediaQuery.sizeOf(sheetContext).height * 0.72,
              child: Column(children: [
                const Padding(
                    padding: EdgeInsets.all(18),
                    child: Text('Choose a doctor',
                        style: TextStyle(
                            fontSize: 20,
                            fontWeight: FontWeight.w700,
                            color: darkGreen))),
                const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 18),
                    child: Text(
                        'Overall order combines patient ratings and experience.',
                        style: TextStyle(color: muted))),
                Expanded(
                    child: ListView.builder(
                        padding: const EdgeInsets.all(12),
                        itemCount: doctors.length,
                        itemBuilder: (context, index) {
                          final item = doctors[index];
                          final details =
                              item['doctorProfile'] as Map<String, dynamic>? ??
                                  {};
                          final rating =
                              item['rating'] as Map<String, dynamic>? ?? {};
                          return Card(
                              child: InkWell(
                                  onTap: item['id'] ==
                                          profile['selectedDoctorId']
                                      ? null
                                      : () => Navigator.pop(
                                          sheetContext, item['id'] as String),
                                  child: Padding(
                                      padding: const EdgeInsets.all(14),
                                      child: Column(
                                          crossAxisAlignment:
                                              CrossAxisAlignment.start,
                                          children: [
                                            Text(
                                                '#${index + 1}  ${details['fullName'] ?? 'Doctor'}',
                                                style: const TextStyle(
                                                    fontWeight: FontWeight.w700,
                                                    color: darkGreen)),
                                            Text(
                                                '${details['specialty'] ?? ''} · ${details['yearsExperience'] ?? '0'} years experience',
                                                style: const TextStyle(
                                                    color: muted)),
                                            Text(rating['average'] == null
                                                ? 'Not rated'
                                                : '${(rating['average'] as num).toStringAsFixed(1)} / 5${rating['sample'] == true ? ' (sample)' : ''}'),
                                            if ('${details['medicalSchool'] ?? ''}'
                                                .isNotEmpty)
                                              Text(
                                                  '${details['medicalSchool']}',
                                                  style: const TextStyle(
                                                      fontSize: 13,
                                                      color: muted)),
                                            if ('${details['bio'] ?? ''}'
                                                .isNotEmpty)
                                              Padding(
                                                  padding:
                                                      const EdgeInsets.only(
                                                          top: 5),
                                                  child: Text(
                                                      '${details['bio']}',
                                                      style: const TextStyle(
                                                          fontSize: 13))),
                                            if (item['id'] ==
                                                profile['selectedDoctorId'])
                                              const Padding(
                                                  padding:
                                                      EdgeInsets.only(top: 6),
                                                  child: Text('Current doctor',
                                                      style: TextStyle(
                                                          color: green,
                                                          fontWeight: FontWeight
                                                              .w700))),
                                          ]))));
                        })),
              ]),
            )));
    if (selected == null || !mounted) return;
    final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
              title: const Text('Send doctor request?'),
              content: const Text(
                  'Your current care-team chat will close. The new doctor can see your records and messages only after accepting.'),
              actions: [
                TextButton(
                    onPressed: () => Navigator.pop(context, false),
                    child: const Text('Cancel')),
                FilledButton(
                    onPressed: () => Navigator.pop(context, true),
                    child: const Text('Send request'))
              ],
            ));
    if (confirmed != true) return;
    try {
      await widget.api.requestDoctor(selected);
      await widget.onRefresh();
      if (mounted) setState(() => actionError = null);
    } catch (error) {
      if (mounted)
        setState(() =>
            actionError = error.toString().replaceFirst('Exception: ', ''));
    }
  }

  Future<void> _contactDialog([Map<String, dynamic>? existing]) async {
    final name =
        TextEditingController(text: '${existing?['contactName'] ?? ''}');
    final relationship =
        TextEditingController(text: '${existing?['relationship'] ?? ''}');
    final phone =
        TextEditingController(text: '${existing?['phoneNumber'] ?? ''}');
    bool primary = existing?['isPrimary'] == true;
    String? dialogError;
    final value = await showDialog<Map<String, dynamic>>(
        context: context,
        builder: (context) => StatefulBuilder(
            builder: (context, update) => AlertDialog(
                  title: Text(existing == null
                      ? 'Add emergency contact'
                      : 'Edit emergency contact'),
                  content: SingleChildScrollView(
                      child: Column(mainAxisSize: MainAxisSize.min, children: [
                    TextField(
                        controller: name,
                        decoration: const InputDecoration(labelText: 'Name')),
                    const SizedBox(height: 10),
                    TextField(
                        controller: relationship,
                        decoration:
                            const InputDecoration(labelText: 'Relationship')),
                    const SizedBox(height: 10),
                    TextField(
                        controller: phone,
                        keyboardType: TextInputType.phone,
                        decoration: const InputDecoration(
                            labelText: 'Phone with country code',
                            hintText: '+201001234567')),
                    CheckboxListTile(
                        contentPadding: EdgeInsets.zero,
                        value: primary,
                        onChanged: (value) =>
                            update(() => primary = value ?? false),
                        title: const Text('Primary contact')),
                    if (dialogError != null)
                      Text(dialogError!,
                          style: const TextStyle(color: Colors.red)),
                  ])),
                  actions: [
                    TextButton(
                        onPressed: () => Navigator.pop(context),
                        child: const Text('Cancel')),
                    FilledButton(
                        onPressed: () {
                          if (name.text.trim().isEmpty ||
                              relationship.text.trim().isEmpty ||
                              !RegExp(r'^\+[1-9][0-9]{5,14}$')
                                  .hasMatch(phone.text)) {
                            update(() => dialogError =
                                'Use a phone number with country code, such as +201001234567.');
                            return;
                          }
                          Navigator.pop(context, {
                            'contactName': name.text.trim(),
                            'relationship': relationship.text.trim(),
                            'phoneNumber': phone.text,
                            'isPrimary': primary
                          });
                        },
                        child: const Text('Save'))
                  ],
                )));
    // The closing dialog animation can still render its fields after showDialog
    // returns, so disposing these controllers here causes a runtime assertion.
    if (value == null || contactsSaving) return;
    setState(() {
      contactsSaving = true;
      contactsError = null;
    });
    try {
      if (existing == null) {
        await widget.api.createEmergencyContact(value);
      } else {
        await widget.api.updateEmergencyContact('${existing['id']}', value);
      }
      await _loadContacts();
    } catch (error) {
      if (mounted)
        setState(() =>
            contactsError = error.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => contactsSaving = false);
    }
  }

  Future<void> _deleteContact(Map<String, dynamic> contact) async {
    if (contactsSaving) return;
    final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
                title: const Text('Delete emergency contact?'),
                content: Text(
                    'Remove ${contact['contactName']} from your contacts?'),
                actions: [
                  TextButton(
                      onPressed: () => Navigator.pop(context, false),
                      child: const Text('Cancel')),
                  FilledButton(
                      onPressed: () => Navigator.pop(context, true),
                      child: const Text('Delete'))
                ]));
    if (confirmed != true) return;
    setState(() => contactsSaving = true);
    try {
      await widget.api.deleteEmergencyContact('${contact['id']}');
      await _loadContacts();
    } catch (error) {
      if (mounted)
        setState(() =>
            contactsError = error.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => contactsSaving = false);
    }
  }

  Future<void> _makePrimary(Map<String, dynamic> contact) async {
    if (contactsSaving || contact['isPrimary'] == true) return;
    setState(() => contactsSaving = true);
    try {
      await widget.api
          .updateEmergencyContact('${contact['id']}', {'isPrimary': true});
      await _loadContacts();
    } catch (error) {
      if (mounted)
        setState(() =>
            contactsError = error.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => contactsSaving = false);
    }
  }

  Widget _care() {
    final doctorProfile =
        doctor?['doctorProfile'] as Map<String, dynamic>? ?? {};
    final connected = assignment?['status'] == 'accepted';
    final messages =
        chronologicalConversationMessages(widget.snapshot['messages']);
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      _panel(
          'Your doctor',
          Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('${doctorProfile['fullName'] ?? 'Doctor request pending'}',
                style: const TextStyle(fontWeight: FontWeight.bold)),
            Text(
                '${doctorProfile['specialty'] ?? ''} · ${doctorProfile['yearsExperience'] ?? '0'} years experience',
                style: const TextStyle(color: muted)),
            const SizedBox(height: 8),
            Text('Request: ${assignment?['status'] ?? 'pending'}'),
            const SizedBox(height: 10),
            OutlinedButton.icon(
                onPressed: _requestDoctor,
                icon: const Icon(Icons.person_search_outlined),
                label: const Text('Find another doctor')),
          ])),
      _panel(
          'Messages',
          Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            if (!connected)
              _empty('Messaging opens after your doctor accepts your request.'),
            if (connected) ...[
              if (messages.isEmpty) _empty('No messages yet.'),
              ...messages.map((item) => PortalMessageBubble(
                  text: '${item['text']}',
                  outgoing: item['from'] == 'patient')),
              TextField(
                  controller: draft,
                  decoration:
                      const InputDecoration(labelText: 'Message your doctor')),
              const SizedBox(height: 8),
              FilledButton.icon(
                  onPressed: () async {
                    final text = draft.text.trim();
                    if (text.isEmpty) return;
                    await add('messages', {
                      'id': nextId,
                      'patientSlug': patientId,
                      'patient': profile['fullName'],
                      'avatar': '',
                      'from': 'patient',
                      'text': text,
                      'time': nowLabel,
                      'sentAt': DateTime.now().toUtc().toIso8601String(),
                      'unread': true
                    });
                    draft.clear();
                    _scrollToLatest(force: true);
                  },
                  icon: const Icon(Icons.send_outlined),
                  label: const Text('Send')),
            ],
          ])),
    ]);
  }

  Future<void> _editProfile() async {
    final updated = await showDialog<Map<String, dynamic>>(
        context: context,
        builder: (_) => _PatientProfileEditor(
            initialProfile: profile, onSave: widget.api.updateProfile));
    if (updated == null || !mounted) return;
    await widget.onAccountUpdated(updated);
    if (mounted) setState(() => actionError = null);
  }

  Widget _profile() =>
      Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        _panel(
            'My information',
            Column(children: [
              _detail('Name', '${profile['fullName'] ?? ''}'),
              _detail('Email', '${widget.account['email'] ?? ''}'),
              _detail('Age', '${profile['age'] ?? ''}'),
              _detail('Weight', '${profile['weight'] ?? ''} kg'),
              _detail('Height', '${profile['height'] ?? ''} cm'),
              _detail('Diabetes type', _profileText(profile['diabetesType'])),
              _detail('Insulin plan', '${profile['insulinPlan'] ?? ''}'),
              _detail('Diagnosis year', '${profile['diagnosisYear'] ?? ''}'),
              _detail('Medications', '${profile['medications'] ?? ''}'),
              _detail('Allergies', '${profile['allergies'] ?? ''}'),
            ]),
            action: TextButton.icon(
                key: const ValueKey('edit-profile'),
                onPressed: _editProfile,
                icon: const Icon(Icons.edit_outlined, size: 18),
                label: const Text('Edit'))),
        if ('${profile['emergencyContact'] ?? ''}'.trim().isNotEmpty)
          _panel(
              'Legacy emergency-contact information',
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('${profile['emergencyContact']}'),
                const SizedBox(height: 6),
                const Text(
                    'Review this text and explicitly add a structured contact. It is not parsed or deleted automatically.',
                    style: TextStyle(color: muted, fontSize: 12))
              ])),
        _panel(
            'Emergency contacts',
            Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              const Text(
                  'Stored for reference only. Adding a contact does not call or alert anyone.',
                  style: TextStyle(color: muted, fontSize: 12)),
              if (contactsLoading)
                const Padding(
                    padding: EdgeInsets.all(12),
                    child: Center(child: CircularProgressIndicator())),
              if (!contactsLoading && contacts.isEmpty)
                _empty('No structured emergency contacts yet.'),
              ...contacts.map((contact) => ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(
                      '${contact['contactName']}${contact['isPrimary'] == true ? ' · Primary' : ''}'),
                  subtitle: Text(
                      '${contact['relationship']} · ${contact['phoneNumber']}'),
                  trailing: PopupMenuButton<String>(
                      enabled: !contactsSaving,
                      onSelected: (action) {
                        if (action == 'edit') _contactDialog(contact);
                        if (action == 'primary') _makePrimary(contact);
                        if (action == 'delete') _deleteContact(contact);
                      },
                      itemBuilder: (_) => [
                            const PopupMenuItem(
                                value: 'edit', child: Text('Edit')),
                            if (contact['isPrimary'] != true)
                              const PopupMenuItem(
                                  value: 'primary',
                                  child: Text('Make primary')),
                            const PopupMenuItem(
                                value: 'delete', child: Text('Delete'))
                          ]))),
              if (contactsError != null)
                Text(contactsError!, style: const TextStyle(color: Colors.red)),
              const SizedBox(height: 8),
              FilledButton.icon(
                  onPressed: contactsSaving ? null : () => _contactDialog(),
                  icon: const Icon(Icons.add),
                  label: Text(contactsSaving ? 'Saving…' : 'Add contact')),
            ])),
        OutlinedButton.icon(
            onPressed: widget.onSignOut,
            icon: const Icon(Icons.logout),
            label: const Text('Sign out')),
      ]);
  Widget _detail(String label, String value) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 7),
      child: Row(children: [
        Expanded(child: Text(label, style: const TextStyle(color: muted))),
        Flexible(
            child: Text(value,
                textAlign: TextAlign.end,
                style: const TextStyle(fontWeight: FontWeight.w600)))
      ]));
}

class _PatientProfileEditor extends StatefulWidget {
  const _PatientProfileEditor(
      {required this.initialProfile, required this.onSave});
  final Map<String, dynamic> initialProfile;
  final Future<Map<String, dynamic>> Function(Map<String, dynamic>) onSave;

  @override
  State<_PatientProfileEditor> createState() => _PatientProfileEditorState();
}

class _PatientProfileEditorState extends State<_PatientProfileEditor> {
  final formKey = GlobalKey<FormState>();
  late final TextEditingController fullName;
  late final TextEditingController age;
  late final TextEditingController weight;
  late final TextEditingController height;
  late final TextEditingController diagnosisYear;
  late final TextEditingController insulinPlan;
  late final TextEditingController medications;
  late final TextEditingController allergies;
  late String diabetesType;
  bool saving = false;
  String? error;

  @override
  void initState() {
    super.initState();
    String value(String key) => '${widget.initialProfile[key] ?? ''}';
    fullName = TextEditingController(text: value('fullName'));
    age = TextEditingController(text: value('age'));
    weight = TextEditingController(text: value('weight'));
    height = TextEditingController(text: value('height'));
    diagnosisYear = TextEditingController(text: value('diagnosisYear'));
    insulinPlan = TextEditingController(text: value('insulinPlan'));
    medications = TextEditingController(text: value('medications'));
    allergies = TextEditingController(text: value('allergies'));
    diabetesType = value('diabetesType');
    if (!const {'', 'Type 1 Diabetes', 'Type 2 Diabetes'}
        .contains(diabetesType)) {
      diabetesType = '';
    }
  }

  @override
  void dispose() {
    fullName.dispose();
    age.dispose();
    weight.dispose();
    height.dispose();
    diagnosisYear.dispose();
    insulinPlan.dispose();
    medications.dispose();
    allergies.dispose();
    super.dispose();
  }

  String? _requiredText(String? value) =>
      value == null || value.trim().isEmpty ? 'This field is required.' : null;

  String? _numberInRange(String? value, String label, double min,
      [double? max]) {
    final number = double.tryParse(value?.trim() ?? '');
    if (number == null ||
        !number.isFinite ||
        number < min ||
        max != null && number > max) {
      return max == null
          ? '$label must be at least ${min.toStringAsFixed(0)}.'
          : '$label must be between ${min.toStringAsFixed(0)} and ${max.toStringAsFixed(0)}.';
    }
    return null;
  }

  String? _optionalNumber(String? value) {
    final text = value?.trim() ?? '';
    if (text.isEmpty) return null;
    return double.tryParse(text)?.isFinite == true
        ? null
        : 'Enter a valid number.';
  }

  Future<void> _save() async {
    if (saving || !(formKey.currentState?.validate() ?? false)) return;
    setState(() {
      saving = true;
      error = null;
    });
    final payload = <String, dynamic>{
      ...widget.initialProfile,
      'fullName': fullName.text.trim(),
      'age': age.text.trim(),
      'weight': weight.text.trim(),
      'height': height.text.trim(),
      'diabetesType': diabetesType,
      'insulinPlan': insulinPlan.text.trim(),
      'diagnosisYear': diagnosisYear.text.trim(),
      'medications': medications.text.trim(),
      'allergies': allergies.text.trim(),
    };
    try {
      final account = await widget.onSave(payload);
      if (mounted) Navigator.of(context).pop(account);
    } catch (failure) {
      if (mounted) {
        setState(() {
          saving = false;
          error = failure.toString().replaceFirst('Exception: ', '');
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        insetPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
        title: const Text('Edit my information'),
        content: SizedBox(
          width: 520,
          child: Form(
            key: formKey,
            child: SingleChildScrollView(
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                TextFormField(
                    key: const ValueKey('profile-full-name'),
                    controller: fullName,
                    validator: _requiredText,
                    textInputAction: TextInputAction.next,
                    decoration: const InputDecoration(labelText: 'Full name')),
                const SizedBox(height: 12),
                TextFormField(
                    key: const ValueKey('profile-age'),
                    controller: age,
                    validator: (value) => _numberInRange(value, 'Age', 1, 120),
                    keyboardType: TextInputType.number,
                    textInputAction: TextInputAction.next,
                    decoration: const InputDecoration(labelText: 'Age')),
                const SizedBox(height: 12),
                TextFormField(
                    key: const ValueKey('profile-weight'),
                    controller: weight,
                    validator: (value) => _numberInRange(value, 'Weight', 1),
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    textInputAction: TextInputAction.next,
                    decoration:
                        const InputDecoration(labelText: 'Weight (kg)')),
                const SizedBox(height: 12),
                TextFormField(
                    key: const ValueKey('profile-height'),
                    controller: height,
                    validator: (value) => _numberInRange(value, 'Height', 1),
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    textInputAction: TextInputAction.next,
                    decoration:
                        const InputDecoration(labelText: 'Height (cm)')),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                    key: const ValueKey('profile-diabetes-type'),
                    initialValue: diabetesType,
                    onChanged: saving
                        ? null
                        : (value) => setState(() => diabetesType = value ?? ''),
                    decoration:
                        const InputDecoration(labelText: 'Diabetes type'),
                    items: const [
                      DropdownMenuItem(value: '', child: Text('Not provided')),
                      DropdownMenuItem(
                          value: 'Type 1 Diabetes',
                          child: Text('Type 1 Diabetes')),
                      DropdownMenuItem(
                          value: 'Type 2 Diabetes',
                          child: Text('Type 2 Diabetes')),
                    ]),
                const SizedBox(height: 12),
                TextFormField(
                    key: const ValueKey('profile-diagnosis-year'),
                    controller: diagnosisYear,
                    validator: _optionalNumber,
                    keyboardType: TextInputType.number,
                    textInputAction: TextInputAction.next,
                    decoration:
                        const InputDecoration(labelText: 'Diagnosis year')),
                const SizedBox(height: 12),
                TextFormField(
                    key: const ValueKey('profile-insulin-plan'),
                    controller: insulinPlan,
                    textInputAction: TextInputAction.next,
                    decoration:
                        const InputDecoration(labelText: 'Insulin plan')),
                const SizedBox(height: 12),
                TextFormField(
                    key: const ValueKey('profile-medications'),
                    controller: medications,
                    textInputAction: TextInputAction.next,
                    decoration:
                        const InputDecoration(labelText: 'Medications')),
                const SizedBox(height: 12),
                TextFormField(
                    key: const ValueKey('profile-allergies'),
                    controller: allergies,
                    decoration: const InputDecoration(labelText: 'Allergies')),
                if (error != null) ...[
                  const SizedBox(height: 12),
                  Align(
                      alignment: Alignment.centerLeft,
                      child: Text(error!,
                          key: const ValueKey('profile-save-error'),
                          style: const TextStyle(color: Colors.red))),
                ],
              ]),
            ),
          ),
        ),
        actions: [
          TextButton(
              key: const ValueKey('cancel-profile-edit'),
              onPressed: saving ? null : () => Navigator.of(context).pop(),
              child: const Text('Cancel')),
          FilledButton(
              key: const ValueKey('save-profile-changes'),
              onPressed: saving ? null : _save,
              child: Text(saving ? 'Saving…' : 'Save changes')),
        ],
      );
}

class _ClinicalEntryDialog extends StatefulWidget {
  const _ClinicalEntryDialog(
      {required this.kind,
      required this.patientId,
      required this.patientName,
      required this.onSave});
  final String kind;
  final String patientId;
  final String patientName;
  final Future<void> Function(Map<String, dynamic>) onSave;
  @override
  State<_ClinicalEntryDialog> createState() => _ClinicalEntryDialogState();
}

class _ClinicalEntryDialogState extends State<_ClinicalEntryDialog> {
  final first = TextEditingController();
  final second = TextEditingController();
  String meal = 'Lunch';
  bool saving = false;
  String? error;

  @override
  void dispose() {
    first.dispose();
    second.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final firstNumber = double.tryParse(first.text);
    if (widget.kind == 'glucose' &&
        (firstNumber == null ||
            !firstNumber.isFinite ||
            firstNumber < 20 ||
            firstNumber > 600)) {
      setState(() => error = 'Enter glucose between 20 and 600 mg/dL.');
      return;
    }
    final foodCarbs = double.tryParse(second.text.trim());
    if (widget.kind == 'food' &&
        (first.text.trim().isEmpty ||
            foodCarbs == null ||
            !foodCarbs.isFinite ||
            foodCarbs < 0)) {
      setState(() => error = 'Enter food and non-negative carbohydrates.');
      return;
    }
    final bolusUnits = double.tryParse(first.text.trim());
    if (widget.kind == 'bolus' &&
        (bolusUnits == null || !bolusUnits.isFinite || bolusUnits < 0)) {
      setState(() => error = 'Enter a finite, non-negative insulin dose.');
      return;
    }
    setState(() {
      saving = true;
      error = null;
    });
    final now = DateTime.now();
    final eventAt = now.toUtc().toIso8601String();
    final id = now.microsecondsSinceEpoch.toRadixString(36);
    final localTimeLabel = TimeOfDay.fromDateTime(now).format(context);
    final common = {
      'id': id,
      'patientSlug': widget.patientId,
      'time': localTimeLabel
    };
    final item = widget.kind == 'glucose'
        ? {...common, 'value': firstNumber, 'recordedAt': eventAt}
        : widget.kind == 'food'
            ? buildMobileFoodEntry(
                id: id,
                patientId: widget.patientId,
                patientName: widget.patientName,
                meal: meal,
                items: first.text.trim(),
                carbs: foodCarbs!,
                submittedAt: now,
                localTimeLabel: localTimeLabel)
            : buildMobileBolusEntry(
                id: id,
                patientId: widget.patientId,
                patientName: widget.patientName,
                units: bolusUnits!,
                submittedAt: now,
                localTimeLabel: localTimeLabel);
    try {
      await widget.onSave(item);
      if (mounted) Navigator.pop(context);
    } catch (failure) {
      if (mounted)
        setState(() {
          saving = false;
          error = 'Not saved: $failure';
        });
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(widget.kind == 'glucose'
            ? 'Record glucose'
            : widget.kind == 'food'
                ? 'Add food'
                : 'Log bolus'),
        content: SingleChildScrollView(
            child: Column(mainAxisSize: MainAxisSize.min, children: [
          if (widget.kind == 'food')
            DropdownButtonFormField<String>(
                initialValue: meal,
                decoration: const InputDecoration(labelText: 'Meal'),
                items: ['Breakfast', 'Lunch', 'Dinner', 'Snack']
                    .map((value) =>
                        DropdownMenuItem(value: value, child: Text(value)))
                    .toList(),
                onChanged:
                    saving ? null : (value) => setState(() => meal = value!)),
          const SizedBox(height: 12),
          TextField(
              enabled: !saving,
              controller: first,
              keyboardType: widget.kind == 'food'
                  ? TextInputType.text
                  : TextInputType.number,
              decoration: InputDecoration(
                  labelText: widget.kind == 'glucose'
                      ? 'Glucose mg/dL'
                      : widget.kind == 'food'
                          ? 'Food items'
                          : 'Bolus units')),
          if (widget.kind == 'food') ...[
            const SizedBox(height: 12),
            TextField(
                enabled: !saving,
                controller: second,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'Carbs g'))
          ],
          if (error != null)
            Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(error!, style: const TextStyle(color: Colors.red))),
        ])),
        actions: [
          TextButton(
              onPressed: saving ? null : () => Navigator.pop(context),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: saving ? null : _save,
              child: Text(saving ? 'Saving…' : 'Save'))
        ],
      );
}

class _ConsumedCarbsDialog extends StatefulWidget {
  const _ConsumedCarbsDialog({this.initial});
  final double? initial;
  @override
  State<_ConsumedCarbsDialog> createState() => _ConsumedCarbsDialogState();
}

class _ConsumedCarbsDialogState extends State<_ConsumedCarbsDialog> {
  late final TextEditingController controller =
      TextEditingController(text: widget.initial?.toString() ?? '');
  String? error;
  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
          title: const Text('Confirm meal'),
          content: Column(mainAxisSize: MainAxisSize.min, children: [
            const Text(
                'Enter the carbohydrates actually consumed. You can keep the announced amount or change it.'),
            const SizedBox(height: 12),
            TextField(
                controller: controller,
                keyboardType: TextInputType.number,
                decoration:
                    const InputDecoration(labelText: 'Consumed carbs g')),
            if (error != null)
              Text(error!, style: const TextStyle(color: Colors.red))
          ]),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('Cancel')),
            FilledButton(
                onPressed: () {
                  final value = double.tryParse(controller.text);
                  if (value == null || value < 0) {
                    setState(() => error = 'Enter a non-negative number.');
                    return;
                  }
                  Navigator.pop(context, value);
                },
                child: const Text('Confirm'))
          ]);
}
