import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'route_names.dart';
import '../../presentation/screens/splash/splash_screen.dart';
import '../../presentation/screens/onboarding/onboarding_screen.dart';
import '../../presentation/screens/auth/login_screen.dart';
import '../../presentation/screens/auth/signup_screen.dart';
import '../../presentation/screens/auth/otp_screen.dart';
import '../../presentation/screens/main/main_shell.dart';
import '../../presentation/screens/home/home_screen.dart';
import '../../presentation/screens/simulation/simulation_screen.dart';
import '../../presentation/screens/insights/insights_screen.dart';
import '../../presentation/screens/profile/profile_screen.dart';
import '../../presentation/screens/doctor/doctor_screen.dart';
import '../../presentation/screens/bolus/bolus_screen.dart';
import '../../presentation/screens/food/food_recommendation_screen.dart';
import '../../presentation/screens/basal/basal_schedule_screen.dart';
import '../../presentation/screens/notifications/notifications_screen.dart';
import '../../presentation/screens/adaptation/adaptation_screen.dart';
import '../../presentation/screens/medical_history/medical_history_screen.dart';
import '../../presentation/screens/subscription/subscription_screen.dart';

final appRouter = GoRouter(
  initialLocation: RouteNames.splash,
  debugLogDiagnostics: false,
  routes: [
    GoRoute(
      path: RouteNames.splash,
      pageBuilder: (ctx, state) => _fade(const SplashScreen(), state),
    ),
    GoRoute(
      path: RouteNames.onboarding,
      pageBuilder: (ctx, state) => _slide(const OnboardingScreen(), state),
    ),
    GoRoute(
      path: RouteNames.login,
      pageBuilder: (ctx, state) => _slide(const LoginScreen(), state),
    ),
    GoRoute(
      path: RouteNames.signup,
      pageBuilder: (ctx, state) => _slide(const SignupScreen(), state),
    ),
    GoRoute(
      path: RouteNames.otp,
      pageBuilder: (ctx, state) => _slide(const OtpScreen(), state),
    ),
    GoRoute(
      path: RouteNames.adaptation,
      pageBuilder: (ctx, state) => _fade(const AdaptationScreen(), state),
    ),
    GoRoute(
      path: RouteNames.bolus,
      pageBuilder: (ctx, state) => _modal(const BolusScreen(), state),
    ),
    GoRoute(
      path: RouteNames.food,
      pageBuilder: (ctx, state) => _modal(const FoodRecommendationScreen(), state),
    ),
    GoRoute(
      path: RouteNames.basal,
      pageBuilder: (ctx, state) => _slide(const BasalScheduleScreen(), state),
    ),
    GoRoute(
      path: RouteNames.notifications,
      pageBuilder: (ctx, state) => _slide(const NotificationsScreen(), state),
    ),
    GoRoute(
      path: RouteNames.medicalHistory,
      pageBuilder: (ctx, state) => _slide(const MedicalHistoryScreen(), state),
    ),
    GoRoute(
      path: RouteNames.subscription,
      pageBuilder: (ctx, state) => _slide(const SubscriptionScreen(), state),
    ),
    ShellRoute(
      pageBuilder: (ctx, state, child) => NoTransitionPage(
        child: MainShell(child: child),
      ),
      routes: [
        GoRoute(
          path: RouteNames.home,
          pageBuilder: (ctx, state) => const NoTransitionPage(child: HomeScreen()),
        ),
        GoRoute(
          path: RouteNames.simulation,
          pageBuilder: (ctx, state) => const NoTransitionPage(child: SimulationScreen()),
        ),
        GoRoute(
          path: RouteNames.insights,
          pageBuilder: (ctx, state) => const NoTransitionPage(child: InsightsScreen()),
        ),
        GoRoute(
          path: RouteNames.doctor,
          pageBuilder: (ctx, state) => const NoTransitionPage(child: DoctorScreen()),
        ),
        GoRoute(
          path: RouteNames.profile,
          pageBuilder: (ctx, state) => const NoTransitionPage(child: ProfileScreen()),
        ),
      ],
    ),
  ],
);

CustomTransitionPage _fade(Widget child, GoRouterState state) =>
    CustomTransitionPage(
      key: state.pageKey,
      child: child,
      transitionDuration: const Duration(milliseconds: 500),
      transitionsBuilder: (ctx, anim, _, c) =>
          FadeTransition(opacity: anim, child: c),
    );

CustomTransitionPage _slide(Widget child, GoRouterState state) =>
    CustomTransitionPage(
      key: state.pageKey,
      child: child,
      transitionDuration: const Duration(milliseconds: 350),
      transitionsBuilder: (ctx, anim, secondary, c) {
        final tween = Tween(
          begin: const Offset(1.0, 0.0),
          end: Offset.zero,
        ).chain(CurveTween(curve: Curves.easeOutCubic));
        return SlideTransition(position: anim.drive(tween), child: c);
      },
    );

CustomTransitionPage _modal(Widget child, GoRouterState state) =>
    CustomTransitionPage(
      key: state.pageKey,
      child: child,
      transitionDuration: const Duration(milliseconds: 400),
      transitionsBuilder: (ctx, anim, _, c) {
        final tween = Tween(
          begin: const Offset(0.0, 1.0),
          end: Offset.zero,
        ).chain(CurveTween(curve: Curves.easeOutQuart));
        return SlideTransition(position: anim.drive(tween), child: c);
      },
    );
