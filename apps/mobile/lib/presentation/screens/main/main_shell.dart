import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../../core/navigation/route_names.dart';
import '../../widgets/navigation/animated_bottom_nav.dart';

class MainShell extends StatelessWidget {
  const MainShell({super.key, required this.child});

  final Widget child;

  static const _routes = [
    RouteNames.home,
    RouteNames.simulation,
    RouteNames.insights,
    RouteNames.doctor,
    RouteNames.profile,
  ];

  int _currentIndex(BuildContext context) {
    final location = GoRouterState.of(context).uri.path;
    final idx = _routes.indexWhere((r) => location.startsWith(r));
    return idx < 0 ? 0 : idx;
  }

  @override
  Widget build(BuildContext context) {
    final index = _currentIndex(context);
    return Scaffold(
      body: child,
      bottomNavigationBar: AnimatedBottomNav(
        currentIndex: index,
        onTap: (i) {
          if (i != index) context.go(_routes[i]);
        },
      ),
    );
  }
}
