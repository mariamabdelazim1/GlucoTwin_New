import 'dart:async';
import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import 'data/sync_api.dart';

const green = Color(0xFF047857);
const darkGreen = Color(0xFF064E3B);
const background = Color(0xFFF4F8F5);
const muted = Color(0xFF667085);

double doctorRank(Map<String, dynamic> doctor) {
  final rating = doctor['rating'] as Map<String, dynamic>? ?? {};
  final profile = doctor['doctorProfile'] as Map<String, dynamic>? ?? {};
  final average = (rating['average'] as num?)?.toDouble() ?? 0;
  final years = (double.tryParse('${profile['yearsExperience'] ?? 0}') ?? 0).clamp(0, 20);
  return (average / 5) * 0.7 + (years / 20) * 0.3;
}

String _profileText(dynamic value) {
  final text = value?.toString() ?? '';
  return text.isEmpty ? 'Not provided' : text;
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
  void initState() { super.initState(); _restore(); }
  Future<void> _restore() async {
    await api.restore();
    if (api.token != null) {
      try { final data = await api.snapshot(); account = data['account'] as Map<String, dynamic>; snapshot = data; _startPolling(); }
      catch (_) { await api.signOut(); }
    }
    if (mounted) setState(() => loading = false);
  }
  void _startPolling() {
    poller?.cancel();
    poller = Timer.periodic(const Duration(seconds: 4), (_) => refresh());
  }
  Future<void> refresh() async {
    try {
      final data = await api.snapshot();
      if (mounted) setState(() { account = data['account'] as Map<String, dynamic>; snapshot = data; error = null; });
    } catch (_) { if (mounted) setState(() => error = 'Connection lost. Showing the last saved view.'); }
  }
  Future<void> signedIn(Map<String, dynamic> value) async {
    setState(() { account = value; loading = true; });
    await refresh(); _startPolling();
    if (mounted) setState(() => loading = false);
  }
  Future<void> signOut() async {
    poller?.cancel(); await api.signOut();
    if (mounted) setState(() { account = null; snapshot = {}; error = null; showWelcome = true; });
  }
  @override
  void dispose() { poller?.cancel(); super.dispose(); }

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Diabetes Digital Twin', debugShowCheckedModeBanner: false,
    theme: ThemeData(
      useMaterial3: true, scaffoldBackgroundColor: background,
      colorScheme: ColorScheme.fromSeed(seedColor: green, primary: green, surface: Colors.white),
      appBarTheme: const AppBarTheme(backgroundColor: Colors.white, foregroundColor: darkGreen),
      inputDecorationTheme: InputDecorationTheme(border: OutlineInputBorder(borderRadius: BorderRadius.circular(6))),
      cardTheme: CardThemeData(color: Colors.white, elevation: 0, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(7), side: const BorderSide(color: Color(0xFFE4E7EC)))),
    ),
    home: loading ? const Scaffold(body: Center(child: CircularProgressIndicator())) : previewWelcome
      ? PatientWelcome(error: error, onSignIn: () => setState(() { previewWelcome = false; showWelcome = false; }), onCreateAccount: () => setState(() { previewWelcome = false; account = null; createAccount = true; showWelcome = false; }))
      : account == null
      ? showWelcome
        ? PatientWelcome(error: error, onSignIn: () => setState(() { createAccount = false; showWelcome = false; }), onCreateAccount: () => setState(() { createAccount = true; showWelcome = false; }))
        : PatientSignIn(key: ValueKey(createAccount), api: api, initialCreating: createAccount, onBack: () => setState(() => showWelcome = true), onSignedIn: signedIn)
      : PatientPortal(api: api, account: account!, snapshot: snapshot, error: error, onRefresh: refresh, onSignOut: signOut),
  );
}

class PatientWelcome extends StatelessWidget {
  const PatientWelcome({super.key, required this.onSignIn, required this.onCreateAccount, this.error});
  final VoidCallback onSignIn;
  final VoidCallback onCreateAccount;
  final String? error;

  @override
  Widget build(BuildContext context) {
    final heroHeight = (MediaQuery.sizeOf(context).height * 0.69).clamp(420.0, 620.0);
    return Scaffold(body: SafeArea(child: ListView(children: [
      SizedBox(height: heroHeight, child: Stack(fit: StackFit.expand, children: [
        Image.asset('assets/images/welcome-monitoring.webp', fit: BoxFit.cover, alignment: Alignment.center),
        Container(color: Colors.black.withValues(alpha: 0.29)),
        const Positioned(left: 22, top: 22, child: Row(children: [Icon(Icons.monitor_heart_outlined, color: Colors.white), SizedBox(width: 8), Text('Diabetes Digital Twin', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w700))])),
        Positioned(left: 22, right: 22, bottom: 24, child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Your care,\nin your pocket.', style: TextStyle(color: Colors.white, fontSize: 35, height: 1.08, fontWeight: FontWeight.w800)),
          const SizedBox(height: 9),
          const Text('Log your day. Stay close to your doctor.', style: TextStyle(color: Colors.white, fontSize: 15)),
          const SizedBox(height: 20),
          SizedBox(width: double.infinity, child: FilledButton(onPressed: onSignIn, style: FilledButton.styleFrom(backgroundColor: green, foregroundColor: Colors.white, padding: const EdgeInsets.symmetric(vertical: 14)), child: const Text('Sign in'))),
          SizedBox(width: double.infinity, child: TextButton(onPressed: onCreateAccount, style: TextButton.styleFrom(foregroundColor: Colors.white), child: const Text('New patient? Create account'))),
        ])),
      ])),
      Padding(padding: const EdgeInsets.all(20), child: Row(children: [
        ClipRRect(borderRadius: BorderRadius.circular(6), child: Image.asset('assets/images/breakfast-log.png', width: 96, height: 96, fit: BoxFit.cover)),
        const SizedBox(width: 16),
        const Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('A little more in sync', style: TextStyle(fontSize: 18, color: darkGreen, fontWeight: FontWeight.w700)),
          SizedBox(height: 5),
          Text('Readings, meals, messages, and your doctor together.', style: TextStyle(color: muted)),
        ])),
      ])),
      if (error != null) Padding(padding: const EdgeInsets.all(20), child: Text(error!, style: const TextStyle(color: Colors.red))),
    ])));
  }
}

class PatientSignIn extends StatefulWidget {
  const PatientSignIn({super.key, required this.api, required this.initialCreating, required this.onBack, required this.onSignedIn});
  final SyncApi api;
  final bool initialCreating;
  final VoidCallback onBack;
  final Future<void> Function(Map<String, dynamic>) onSignedIn;
  @override
  State<PatientSignIn> createState() => _PatientSignInState();
}

class _PatientSignInState extends State<PatientSignIn> {
  final key = GlobalKey<FormState>();
  final email = TextEditingController(); final password = TextEditingController();
  final name = TextEditingController(); final age = TextEditingController();
  final weight = TextEditingController(); final height = TextEditingController();
  bool creating = false; bool busy = false;
  String? error; String? doctorId;
  List<dynamic> doctors = [];

  @override
  void initState() { super.initState(); creating = widget.initialCreating; _loadDoctors(); }
  Future<void> _loadDoctors() async {
    try {
      final value = await widget.api.doctors();
      value.sort((a, b) => doctorRank(b as Map<String, dynamic>).compareTo(doctorRank(a as Map<String, dynamic>)));
      if (mounted) setState(() => doctors = value);
    }
    catch (_) { if (mounted) setState(() => error = 'Connect to the sync service to see doctors.'); }
  }
  Future<void> _submit() async {
    if (!key.currentState!.validate()) return;
    if (creating && doctorId == null) { setState(() => error = 'Choose a doctor.'); return; }
    setState(() { busy = true; error = null; });
    try {
      final result = creating ? await widget.api.register({
        'id': DateTime.now().microsecondsSinceEpoch.toRadixString(36), 'role': 'patient',
        'email': email.text.trim().toLowerCase(), 'password': password.text,
        'patientProfile': {'fullName': name.text.trim(), 'age': age.text, 'weight': weight.text,
          'height': height.text, 'diabetesType': '', 'insulinPlan': '', 'diagnosisYear': '',
          'medications': '', 'allergies': '', 'emergencyContact': '', 'selectedDoctorId': doctorId},
      }) : await widget.api.login(email.text.trim(), password.text);
      await widget.onSignedIn(result);
    } catch (e) { if (mounted) setState(() => error = e.toString().replaceFirst('Exception: ', '')); }
    if (mounted) setState(() => busy = false);
  }
  @override
  void dispose() { for (final controller in [email, password, name, age, weight, height]) { controller.dispose(); } super.dispose(); }
  @override
  Widget build(BuildContext context) => Scaffold(body: SafeArea(child: Center(child: ConstrainedBox(
    constraints: const BoxConstraints(maxWidth: 480),
    child: SingleChildScrollView(padding: const EdgeInsets.all(24), child: Form(key: key, child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Align(alignment: Alignment.centerLeft, child: IconButton(tooltip: 'Back to welcome', onPressed: widget.onBack, icon: const Icon(Icons.arrow_back, color: darkGreen))),
      const Icon(Icons.monitor_heart_outlined, color: green, size: 42), const SizedBox(height: 16),
      const Text('Diabetes Digital Twin', style: TextStyle(fontSize: 25, fontWeight: FontWeight.bold, color: darkGreen)),
      Text(creating ? 'Create your patient account' : 'Patient sign in', style: const TextStyle(color: muted)),
      if (!creating) ...[
        const SizedBox(height: 18),
        const Text('Saved account', style: TextStyle(fontWeight: FontWeight.w600, color: darkGreen)),
        ListTile(contentPadding: EdgeInsets.zero, leading: const CircleAvatar(backgroundColor: Color(0xFFEEF7F1), child: Text('OH', style: TextStyle(color: green))), title: const Text('Omar Hassan'), subtitle: const Text('omar.hassan@example.com'), onTap: busy ? null : () { email.text = 'omar.hassan@example.com'; password.text = 'password'; setState(() => error = null); }),
      ],
      const SizedBox(height: 28),
      if (creating) ...[
        TextFormField(controller: name, decoration: const InputDecoration(labelText: 'Full name'), validator: (v) => v == null || v.trim().isEmpty ? 'Enter your name' : null), const SizedBox(height: 12),
        Row(children: [Expanded(child: TextFormField(controller: age, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Age'), validator: (v) => (int.tryParse(v ?? '') ?? 0) < 1 ? 'Enter age' : null)), const SizedBox(width: 12), Expanded(child: TextFormField(controller: weight, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Weight kg'), validator: (v) => (double.tryParse(v ?? '') ?? 0) <= 0 ? 'Enter weight' : null))]),
        const SizedBox(height: 12),
        TextFormField(controller: height, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Height cm'), validator: (v) => (double.tryParse(v ?? '') ?? 0) <= 0 ? 'Enter height' : null),
        const SizedBox(height: 12),
        const SizedBox(height: 16), const Text('Choose your doctor', style: TextStyle(fontWeight: FontWeight.w700)),
        ...doctors.asMap().entries.map((entry) { final doctor = entry.value as Map<String, dynamic>; final profile = doctor['doctorProfile'] as Map<String, dynamic>? ?? {}; final rating = doctor['rating'] as Map<String, dynamic>? ?? {}; final selected = doctorId == doctor['id']; return Card(child: InkWell(onTap: () => setState(() => doctorId = doctor['id'] as String), child: Padding(padding: const EdgeInsets.all(12), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [Icon(selected ? Icons.radio_button_checked : Icons.radio_button_off, color: green), const SizedBox(width: 10), Expanded(child: Text('#${entry.key + 1}  ${profile['fullName'] ?? 'Doctor'}', style: const TextStyle(fontWeight: FontWeight.w700)))]),
          Padding(padding: const EdgeInsets.only(left: 34, top: 4), child: Text('${profile['specialty'] ?? ''} · ${profile['yearsExperience'] ?? '0'} years experience', style: const TextStyle(color: muted))),
          Padding(padding: const EdgeInsets.only(left: 34, top: 4), child: Text(rating['average'] == null ? 'No ratings yet' : '${(rating['average'] as num).toStringAsFixed(1)} / 5 · ${rating['count']} ratings${rating['sample'] == true ? ' (sample)' : ''}', style: const TextStyle(color: darkGreen, fontSize: 13))),
          if (profile['medicalSchool'] != null) Padding(padding: const EdgeInsets.fromLTRB(16, 0, 16, 8), child: Text('${profile['medicalSchool']}', style: const TextStyle(color: muted, fontSize: 13))),
          if ('${profile['qualifications'] ?? ''}'.isNotEmpty) Padding(padding: const EdgeInsets.fromLTRB(16, 0, 16, 8), child: Text('Qualifications: ${profile['qualifications']}', style: const TextStyle(fontSize: 13))),
          if (profile['certificates'] is List && (profile['certificates'] as List).isNotEmpty) Padding(padding: const EdgeInsets.fromLTRB(16, 0, 16, 8), child: Text('Certificates: ${(profile['certificates'] as List).join(', ')}', style: const TextStyle(fontSize: 13))),
          if (profile['papers'] is List && (profile['papers'] as List).isNotEmpty) Padding(padding: const EdgeInsets.fromLTRB(16, 0, 16, 8), child: Text('Papers: ${(profile['papers'] as List).join(', ')}', style: const TextStyle(fontSize: 13))),
          if (profile['bio'] != null) Padding(padding: const EdgeInsets.fromLTRB(16, 0, 16, 12), child: Text('${profile['bio']}', style: const TextStyle(fontSize: 13))),
        ])))); }),
      ],
      TextFormField(controller: email, keyboardType: TextInputType.emailAddress, decoration: const InputDecoration(labelText: 'Email'), validator: (v) => v == null || !v.contains('@') ? 'Enter a valid email' : null), const SizedBox(height: 12),
      TextFormField(controller: password, obscureText: true, decoration: const InputDecoration(labelText: 'Password'), validator: (v) => v == null || v.length < (creating ? 8 : 1) ? 'Enter your password' : null),
      if (error != null) Padding(padding: const EdgeInsets.only(top: 12), child: Text(error!, style: const TextStyle(color: Colors.red))),
      const SizedBox(height: 20), FilledButton(onPressed: busy ? null : _submit, child: Text(busy ? 'Please wait...' : creating ? 'Create account' : 'Sign in')),
      TextButton(onPressed: () => setState(() { creating = !creating; error = null; }), child: Text(creating ? 'Already have an account? Sign in' : 'New patient? Create account')),
    ]))),
  ))));
}

class PatientPortal extends StatefulWidget {
  const PatientPortal({super.key, required this.api, required this.account, required this.snapshot, required this.error, required this.onRefresh, required this.onSignOut});
  final SyncApi api;
  final Map<String, dynamic> account;
  final Map<String, dynamic> snapshot;
  final String? error;
  final Future<void> Function() onRefresh;
  final Future<void> Function() onSignOut;
  @override
  State<PatientPortal> createState() => _PatientPortalState();
}

class _PatientPortalState extends State<PatientPortal> {
  int tab = 0;
  @override
  void initState() {
    super.initState();
    tab = switch (Uri.base.queryParameters['view']) { 'record' => 1, 'care' => 2, 'profile' => 3, _ => 0 };
  }
  String? actionError;
  final draft = TextEditingController();
  List<dynamic> list(String key) => widget.snapshot[key] as List<dynamic>? ?? [];
  Map<String, dynamic> get profile => widget.account['patientProfile'] as Map<String, dynamic>? ?? {};
  String get patientId => widget.account['id'] as String;
  Map<String, dynamic>? get assignment {
    for (final raw in list('assignments')) { final item = raw as Map<String, dynamic>; if (item['patientId'] == patientId && item['doctorId'] == profile['selectedDoctorId']) return item; }
    return null;
  }
  Map<String, dynamic>? get doctor {
    for (final raw in list('doctors')) { final item = raw as Map<String, dynamic>; if (item['id'] == profile['selectedDoctorId']) return item; }
    return null;
  }
  Future<void> add(String kind, Map<String, dynamic> item) async {
    try { await widget.api.add(kind, item); await widget.onRefresh(); if (mounted) setState(() => actionError = null); }
    catch (e) { if (mounted) setState(() => actionError = e.toString().replaceFirst('Exception: ', '')); }
  }
  String get nowLabel => TimeOfDay.now().format(context);
  String get nextId => DateTime.now().microsecondsSinceEpoch.toRadixString(36);
  @override
  void dispose() { draft.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    final titles = ['Overview', 'Record', 'Care team', 'Profile'];
    return Scaffold(
      appBar: AppBar(title: Text(titles[tab]), actions: [IconButton(tooltip: 'Refresh', onPressed: widget.onRefresh, icon: const Icon(Icons.refresh))]),
      body: RefreshIndicator(onRefresh: widget.onRefresh, child: ListView(padding: const EdgeInsets.all(16), children: [
        if (widget.error != null) _notice(widget.error!),
        if (actionError != null) _notice(actionError!),
        if (tab == 0) _overview(), if (tab == 1) _records(), if (tab == 2) _care(), if (tab == 3) _profile(),
      ])),
      bottomNavigationBar: NavigationBar(selectedIndex: tab, onDestinationSelected: (value) => setState(() => tab = value), destinations: const [
        NavigationDestination(icon: Icon(Icons.space_dashboard_outlined), label: 'Overview'),
        NavigationDestination(icon: Icon(Icons.add_chart_outlined), label: 'Record'),
        NavigationDestination(icon: Icon(Icons.forum_outlined), label: 'Care'),
        NavigationDestination(icon: Icon(Icons.person_outline), label: 'Profile'),
      ]),
    );
  }

  Widget _notice(String message) => Padding(padding: const EdgeInsets.only(bottom: 12), child: DecoratedBox(decoration: BoxDecoration(color: const Color(0xFFFFF7ED), borderRadius: BorderRadius.circular(6)), child: Padding(padding: const EdgeInsets.all(12), child: Text(message))));
  Widget _panel(String title, Widget child) => Card(child: Padding(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(title, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.bold, color: darkGreen)), const SizedBox(height: 12), child])));
  Widget _empty(String text) => Text(text, style: const TextStyle(color: muted));

  Widget _overview() {
    final readings = list('glucose').cast<Map<String, dynamic>>()..sort((a, b) => (a['recordedAt'] as String).compareTo(b['recordedAt'] as String));
    final latest = readings.isEmpty ? null : readings.last;
    final chartReadings = readings.length > 12 ? readings.sublist(readings.length - 12) : readings;
    final food = list('food').cast<Map<String, dynamic>>();
    final bolus = list('bolus').cast<Map<String, dynamic>>();
    final messages = list('messages').cast<Map<String, dynamic>>();
    final demo = widget.snapshot['demo'] as Map<String, dynamic>?;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Text('Hello, ${profile['fullName'] ?? 'Patient'}', style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold, color: darkGreen)),
      const SizedBox(height: 4), const Text('Your readings and care records', style: TextStyle(color: muted)), const SizedBox(height: 16),
      if (demo != null) ..._demoDashboard(demo),
      Row(children: [Expanded(child: FilledButton.icon(onPressed: () => setState(() => tab = 1), icon: const Icon(Icons.add), label: const Text('Record'))), const SizedBox(width: 8), Expanded(child: OutlinedButton.icon(onPressed: () => setState(() => tab = 2), icon: const Icon(Icons.chat_bubble_outline), label: const Text('Care team')))]),
      const SizedBox(height: 8),
      _panel('Latest manual reading', latest == null ? _empty('No readings yet. Record a glucose value to begin.') : Row(crossAxisAlignment: CrossAxisAlignment.end, children: [Text('${latest['value']}', style: const TextStyle(fontSize: 42, fontWeight: FontWeight.bold, color: darkGreen)), const Padding(padding: EdgeInsets.only(bottom: 7, left: 5), child: Text('mg/dL')), const Spacer(), Text('${latest['time']}', style: const TextStyle(color: muted))])),
      if (chartReadings.length >= 2) _panel('Reading trend', SizedBox(height: 190, child: LineChart(LineChartData(
        gridData: const FlGridData(show: true), borderData: FlBorderData(show: false), titlesData: const FlTitlesData(show: false),
        lineBarsData: [LineChartBarData(spots: chartReadings.asMap().entries.map((entry) => FlSpot(entry.key.toDouble(), (entry.value['value'] as num).toDouble())).toList(), isCurved: false, color: green, barWidth: 3, dotData: const FlDotData(show: true))],
      )))),
      _panel('Recorded totals', Column(children: [
        _countRow(Icons.bloodtype_outlined, 'Manual readings', readings.length),
        _countRow(Icons.restaurant_outlined, 'Food entries', list('food').length),
        _countRow(Icons.vaccines_outlined, 'Bolus logs', list('bolus').length),
      ])),
      _panel('Care status', Text(assignment?['status'] == 'accepted' ? 'Connected to ${doctor?['doctorProfile']?['fullName'] ?? 'your doctor'}' : 'Doctor request ${assignment?['status'] ?? 'pending'}')),
      _panel('Recent food', food.isEmpty ? _empty('No food entries yet.') : Column(children: food.take(3).map((item) => ListTile(contentPadding: EdgeInsets.zero, leading: const Icon(Icons.restaurant_outlined, color: green), title: Text('${item['meal']}: ${item['items']}'), subtitle: Text('${item['carbs']} carbs'), trailing: Text('${item['time'] ?? ''}'))).toList())),
      _panel('Manual bolus log', bolus.isEmpty ? _empty('No bolus logs yet.') : Column(children: bolus.take(3).map((item) => ListTile(contentPadding: EdgeInsets.zero, leading: const Icon(Icons.vaccines_outlined, color: green), title: Text('${item['recorded']} · ${item['meal']}'), subtitle: Text('Carbs ${item['carbs']} · Pre-meal ${item['preMeal']}'), trailing: Text('${item['time'] ?? ''}'))).toList())),
      _panel('Care-team messages', messages.isEmpty ? _empty(assignment?['status'] == 'accepted' ? 'No messages yet.' : 'Messaging opens when your doctor accepts.') : Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text('${messages.first['from'] == 'patient' ? 'You' : doctor?['doctorProfile']?['fullName'] ?? 'Doctor'}: ${messages.first['text']}', maxLines: 2, overflow: TextOverflow.ellipsis), const SizedBox(height: 8), TextButton.icon(onPressed: () => setState(() => tab = 2), icon: const Icon(Icons.arrow_forward), label: const Text('Open conversation'))])),
      _panel('My medical info', Column(children: [_detail('Age', '${profile['age'] ?? ''}'), _detail('Weight', '${profile['weight'] ?? ''} kg'), _detail('Height', '${profile['height'] ?? ''} cm'), _detail('Diabetes type', _profileText(profile['diabetesType'])), _detail('Insulin plan', '${profile['insulinPlan'] ?? 'Not added'}')])),
      if (demo == null) ...[
        _panel('CGM and digital twin', _empty('No connected CGM or validated forecast is available. Manual readings above are your recorded values.')),
        _notice('No live CGM or validated prediction feed is connected. These are manually entered values, not treatment recommendations.'),
      ],
    ]);
  }

  List<Widget> _demoDashboard(Map<String, dynamic> demo) {
    final summary = demo['summary'] as Map<String, dynamic>;
    final cgm = (demo['cgm'] as List).cast<Map<String, dynamic>>();
    final forecast = (demo['forecast'] as List).cast<Map<String, dynamic>>();
    return [
      _notice('Demo patient: sample CGM readings, forecasts, and historical logs. This is not a live sensor feed.'),
      _panel('Current glucose', Row(crossAxisAlignment: CrossAxisAlignment.end, children: [Text('${summary['currentGlucose']}', style: const TextStyle(fontSize: 42, fontWeight: FontWeight.w800, color: darkGreen)), const Padding(padding: EdgeInsets.only(left: 6, bottom: 8), child: Text('mg/dL')), const Spacer(), Text('${summary['trend']}', style: const TextStyle(color: green, fontWeight: FontWeight.w600))])),
      _panel('Glucose summary', Column(children: [_detail('Time in range', '${summary['timeInRange']}%'), _detail('Average glucose', '${summary['averageGlucose']} mg/dL'), _detail('Last CGM reading', '${summary['lastReading']}')])),
      _panel('CGM graph', _sampleChart(cgm, forecast: false)),
      _panel('Predicted glucose · demo', Column(children: (demo['forecastSnapshots'] as List).map((raw) { final item = raw as Map<String, dynamic>; return _detail('After ${item['horizon']}', '${item['glucose']} mg/dL · ${item['trend']}'); }).toList())),
      _panel('Digital twin forecast · demo', Column(crossAxisAlignment: CrossAxisAlignment.start, children: [_sampleChart(forecast, forecast: true), const SizedBox(height: 8), const Text('Green: sample history. Amber: simulated forecast.', style: TextStyle(fontSize: 12, color: muted))])),
    ];
  }

  Widget _sampleChart(List<Map<String, dynamic>> rows, {required bool forecast}) {
    List<FlSpot> points(String key) => rows.asMap().entries.where((entry) => entry.value[key] is num).map((entry) => FlSpot(entry.key.toDouble(), (entry.value[key] as num).toDouble())).toList();
    return SizedBox(height: 215, child: Padding(padding: const EdgeInsets.only(top: 8, right: 12), child: LineChart(LineChartData(
      minY: 80, maxY: 260, minX: 0, maxX: (rows.length - 1).toDouble(),
      gridData: const FlGridData(show: true, drawVerticalLine: false, horizontalInterval: 60),
      borderData: FlBorderData(show: false),
      titlesData: FlTitlesData(
        topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        leftTitles: AxisTitles(sideTitles: SideTitles(showTitles: true, reservedSize: 32, interval: 60, getTitlesWidget: (value, meta) => Text('${value.toInt()}', style: const TextStyle(fontSize: 10, color: muted)))),
        bottomTitles: AxisTitles(sideTitles: SideTitles(showTitles: true, reservedSize: 26, interval: forecast ? 3 : 6, getTitlesWidget: (value, meta) {
          final index = value.toInt();
          if (index < 0 || index >= rows.length) return const SizedBox.shrink();
          return Padding(padding: const EdgeInsets.only(top: 7), child: Text('${rows[index]['time']}', style: const TextStyle(fontSize: 10, color: muted)));
        })),
      ),
      lineBarsData: [
        LineChartBarData(spots: points(forecast ? 'historical' : 'glucose'), color: green, barWidth: 2.5, dotData: const FlDotData(show: false), belowBarData: BarAreaData(show: !forecast, color: green.withValues(alpha: 0.08))),
        if (forecast) LineChartBarData(spots: [FlSpot(7, (rows[7]['historical'] as num).toDouble()), ...points('predicted')], color: const Color(0xFFC68A19), dashArray: [5, 4], barWidth: 2.5, dotData: const FlDotData(show: false)),
      ],
    ))));
  }
  Widget _countRow(IconData icon, String label, int count) => Padding(padding: const EdgeInsets.symmetric(vertical: 7), child: Row(children: [Icon(icon, color: green, size: 20), const SizedBox(width: 9), Expanded(child: Text(label)), Text('$count', style: const TextStyle(fontWeight: FontWeight.bold))]));

  Widget _records() => Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
    _panel('Glucose', Column(crossAxisAlignment: CrossAxisAlignment.start, children: [FilledButton.icon(onPressed: () => _entryDialog('glucose'), icon: const Icon(Icons.add), label: const Text('Record reading')), const SizedBox(height: 8), ...list('glucose').take(5).map((raw) { final item = raw as Map<String, dynamic>; return ListTile(contentPadding: EdgeInsets.zero, title: Text('${item['value']} mg/dL'), trailing: Text('${item['time']}')); }), if (list('glucose').isEmpty) _empty('No readings yet.') ])),
    _panel('Food', Column(crossAxisAlignment: CrossAxisAlignment.start, children: [FilledButton.icon(onPressed: () => _entryDialog('food'), icon: const Icon(Icons.add), label: const Text('Add food')), const SizedBox(height: 8), ...list('food').take(5).map((raw) { final item = raw as Map<String, dynamic>; return ListTile(contentPadding: EdgeInsets.zero, title: Text('${item['meal']}: ${item['items']}'), subtitle: Text('${item['carbs']} carbs'), trailing: Text('${item['time']}')); }), if (list('food').isEmpty) _empty('No food entries yet.') ])),
    _panel('Manual bolus', Column(crossAxisAlignment: CrossAxisAlignment.start, children: [FilledButton.icon(onPressed: () => _entryDialog('bolus'), icon: const Icon(Icons.add), label: const Text('Log bolus')), const SizedBox(height: 8), ...list('bolus').take(5).map((raw) { final item = raw as Map<String, dynamic>; return ListTile(contentPadding: EdgeInsets.zero, title: Text('${item['recorded']} at ${item['meal']}'), subtitle: Text('${item['carbs']} carbs · ${item['preMeal']} pre-meal'), trailing: Text('${item['time']}')); }), if (list('bolus').isEmpty) _empty('No bolus logs yet.') ])),
  ]);

  Future<void> _entryDialog(String kind) async {
    final first = TextEditingController(); final second = TextEditingController(); final third = TextEditingController();
    String meal = 'Lunch';
    final result = await showDialog<Map<String, dynamic>>(context: context, builder: (context) => StatefulBuilder(builder: (context, update) => AlertDialog(
      title: Text(kind == 'glucose' ? 'Record glucose' : kind == 'food' ? 'Add food' : 'Log bolus'),
      content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
        if (kind != 'glucose') DropdownButtonFormField<String>(initialValue: meal, decoration: const InputDecoration(labelText: 'Meal'), items: ['Breakfast', 'Lunch', 'Dinner', 'Snack'].map((v) => DropdownMenuItem(value: v, child: Text(v))).toList(), onChanged: (v) => update(() => meal = v!)),
        const SizedBox(height: 12),
        TextField(controller: first, keyboardType: kind == 'food' ? TextInputType.text : TextInputType.number, decoration: InputDecoration(labelText: kind == 'glucose' ? 'Glucose mg/dL' : kind == 'food' ? 'Food items' : 'Carbs g')),
        if (kind != 'glucose') ...[const SizedBox(height: 12), TextField(controller: second, keyboardType: TextInputType.number, decoration: InputDecoration(labelText: kind == 'food' ? 'Carbs g' : 'Pre-meal glucose mg/dL'))],
        if (kind == 'bolus') ...[const SizedBox(height: 12), TextField(controller: third, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Bolus units'))],
      ])),
      actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')), FilledButton(onPressed: () {
        final firstNumber = double.tryParse(first.text);
        if (kind == 'glucose' && (firstNumber == null || firstNumber < 20 || firstNumber > 600)) return;
        if (kind == 'food' && (first.text.trim().isEmpty || (double.tryParse(second.text) ?? -1) < 0)) return;
        if (kind == 'bolus' && ((firstNumber ?? -1) < 0 || (double.tryParse(second.text) ?? -1) < 20 || (double.tryParse(third.text) ?? -1) < 0)) return;
        final common = {'id': nextId, 'patientSlug': patientId, 'time': nowLabel};
        final item = kind == 'glucose' ? {...common, 'value': firstNumber, 'recordedAt': DateTime.now().toUtc().toIso8601String()}
          : kind == 'food' ? {...common, 'patient': profile['fullName'], 'meal': meal, 'items': first.text.trim(), 'carbs': '${second.text}g', 'impact': 'Pending CGM impact', 'status': 'Recorded'}
          : {...common, 'patient': profile['fullName'], 'meal': meal, 'carbs': '${first.text}g', 'preMeal': '${second.text} mg/dL', 'recommended': 'Doctor review', 'recorded': '${third.text} U'};
        Navigator.pop(context, item);
      }, child: const Text('Save'))],
    )));
    first.dispose(); second.dispose(); third.dispose();
    if (result != null) await add(kind, result);
  }

  Future<void> _requestDoctor() async {
    final doctors = list('doctors').cast<Map<String, dynamic>>()..sort((a, b) => doctorRank(b).compareTo(doctorRank(a)));
    final selected = await showModalBottomSheet<String>(context: context, isScrollControlled: true, builder: (sheetContext) => SafeArea(child: SizedBox(
      height: MediaQuery.sizeOf(sheetContext).height * 0.72,
      child: Column(children: [
        const Padding(padding: EdgeInsets.all(18), child: Text('Choose a doctor', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: darkGreen))),
        const Padding(padding: EdgeInsets.symmetric(horizontal: 18), child: Text('Overall order combines patient ratings and experience.', style: TextStyle(color: muted))),
        Expanded(child: ListView.builder(padding: const EdgeInsets.all(12), itemCount: doctors.length, itemBuilder: (context, index) {
          final item = doctors[index];
          final details = item['doctorProfile'] as Map<String, dynamic>? ?? {};
          final rating = item['rating'] as Map<String, dynamic>? ?? {};
          return Card(child: InkWell(onTap: item['id'] == profile['selectedDoctorId'] ? null : () => Navigator.pop(sheetContext, item['id'] as String), child: Padding(padding: const EdgeInsets.all(14), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('#${index + 1}  ${details['fullName'] ?? 'Doctor'}', style: const TextStyle(fontWeight: FontWeight.w700, color: darkGreen)),
            Text('${details['specialty'] ?? ''} · ${details['yearsExperience'] ?? '0'} years experience', style: const TextStyle(color: muted)),
            Text(rating['average'] == null ? 'Not rated' : '${(rating['average'] as num).toStringAsFixed(1)} / 5${rating['sample'] == true ? ' (sample)' : ''}'),
            if ('${details['medicalSchool'] ?? ''}'.isNotEmpty) Text('${details['medicalSchool']}', style: const TextStyle(fontSize: 13, color: muted)),
            if ('${details['bio'] ?? ''}'.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 5), child: Text('${details['bio']}', style: const TextStyle(fontSize: 13))),
            if (item['id'] == profile['selectedDoctorId']) const Padding(padding: EdgeInsets.only(top: 6), child: Text('Current doctor', style: TextStyle(color: green, fontWeight: FontWeight.w700))),
          ]))));
        })),
      ]),
    )));
    if (selected == null || !mounted) return;
    final confirmed = await showDialog<bool>(context: context, builder: (context) => AlertDialog(
      title: const Text('Send doctor request?'),
      content: const Text('Your current care-team chat will close. The new doctor can see your records and messages only after accepting.'),
      actions: [TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')), FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Send request'))],
    ));
    if (confirmed != true) return;
    try {
      await widget.api.requestDoctor(selected);
      await widget.onRefresh();
      if (mounted) setState(() => actionError = null);
    } catch (error) {
      if (mounted) setState(() => actionError = error.toString().replaceFirst('Exception: ', ''));
    }
  }

  Widget _care() {
    final doctorProfile = doctor?['doctorProfile'] as Map<String, dynamic>? ?? {};
    final connected = assignment?['status'] == 'accepted';
    final messages = list('messages').cast<Map<String, dynamic>>().reversed.toList();
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      _panel('Your doctor', Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('${doctorProfile['fullName'] ?? 'Doctor request pending'}', style: const TextStyle(fontWeight: FontWeight.bold)),
        Text('${doctorProfile['specialty'] ?? ''} · ${doctorProfile['yearsExperience'] ?? '0'} years experience', style: const TextStyle(color: muted)),
        const SizedBox(height: 8), Text('Request: ${assignment?['status'] ?? 'pending'}'),
        const SizedBox(height: 10), OutlinedButton.icon(onPressed: _requestDoctor, icon: const Icon(Icons.person_search_outlined), label: const Text('Find another doctor')),
      ])),
      _panel('Messages', Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        if (!connected) _empty('Messaging opens after your doctor accepts your request.'),
        if (connected) ...[
          if (messages.isEmpty) _empty('No messages yet.'),
          ...messages.map((item) => Align(alignment: item['from'] == 'patient' ? Alignment.centerRight : Alignment.centerLeft, child: Container(margin: const EdgeInsets.symmetric(vertical: 4), padding: const EdgeInsets.all(10), decoration: BoxDecoration(color: item['from'] == 'patient' ? const Color(0xFFEEF7F1) : Colors.white, border: Border.all(color: const Color(0xFFE4E7EC)), borderRadius: BorderRadius.circular(6)), child: Text('${item['text']}')))),
          TextField(controller: draft, decoration: const InputDecoration(labelText: 'Message your doctor')),
          const SizedBox(height: 8),
          FilledButton.icon(onPressed: () async { final text = draft.text.trim(); if (text.isEmpty) return; await add('messages', {'id': nextId, 'patientSlug': patientId, 'patient': profile['fullName'], 'avatar': '', 'from': 'patient', 'text': text, 'time': nowLabel, 'unread': true}); draft.clear(); }, icon: const Icon(Icons.send_outlined), label: const Text('Send')),
        ],
      ])),
    ]);
  }

  Widget _profile() => Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
    _panel('My information', Column(children: [
      _detail('Name', '${profile['fullName'] ?? ''}'), _detail('Email', '${widget.account['email'] ?? ''}'),
      _detail('Age', '${profile['age'] ?? ''}'), _detail('Weight', '${profile['weight'] ?? ''} kg'),
      _detail('Height', '${profile['height'] ?? ''} cm'), _detail('Diabetes type', _profileText(profile['diabetesType'])),
      _detail('Insulin plan', '${profile['insulinPlan'] ?? ''}'),
      _detail('Diagnosis year', '${profile['diagnosisYear'] ?? ''}'),
      _detail('Medications', '${profile['medications'] ?? ''}'),
      _detail('Allergies', '${profile['allergies'] ?? ''}'),
      _detail('Emergency contact', '${profile['emergencyContact'] ?? ''}'),
    ])),
    _panel('Basal plan', _empty('An AI-suggested basal schedule requires confirmation by your doctor. No confirmed schedule is available here yet.')),
    OutlinedButton.icon(onPressed: widget.onSignOut, icon: const Icon(Icons.logout), label: const Text('Sign out')),
  ]);
  Widget _detail(String label, String value) => Padding(padding: const EdgeInsets.symmetric(vertical: 7), child: Row(children: [Expanded(child: Text(label, style: const TextStyle(color: muted))), Flexible(child: Text(value, textAlign: TextAlign.end, style: const TextStyle(fontWeight: FontWeight.w600)))]));
}
