import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import '../../../core/constants/app_colors.dart';
import '../../../core/constants/app_spacing.dart';
import '../../../core/navigation/route_names.dart';
import '../../../core/utils/theme_ext.dart';
import '../../widgets/common/gradient_button.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _emailCtrl = TextEditingController();
  final _passCtrl = TextEditingController();
  bool _obscure = true;
  bool _loading = false;
  final _formKey = GlobalKey<FormState>();

  @override
  void dispose() {
    _emailCtrl.dispose();
    _passCtrl.dispose();
    super.dispose();
  }

  void _login() {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _loading = true);
    Future.delayed(const Duration(milliseconds: 1500), () {
      if (mounted) context.go(RouteNames.home);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: context.appBg,
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(AppSpacing.screenPadding),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: 20),

              _buildHeader(context),

              const SizedBox(height: 48),

              Form(
                key: _formKey,
                child: _buildForm(context),
              )
                  .animate(delay: 200.ms)
                  .fadeIn(duration: 500.ms)
                  .slideY(begin: 0.2, end: 0, duration: 500.ms),

              const SizedBox(height: 32),

              GradientButton(
                label: 'Sign In',
                onPressed: _login,
                isLoading: _loading,
                icon: Icons.login_rounded,
              ).animate(delay: 400.ms).fadeIn(duration: 400.ms),

              const SizedBox(height: 16),

              _BiometricButton()
                  .animate(delay: 500.ms)
                  .fadeIn(duration: 400.ms),

              const SizedBox(height: 40),

              Row(children: [
                Expanded(child: Divider(color: context.borderC)),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Text('or continue with',
                      style: TextStyle(
                          color: context.textMut, fontSize: 12)),
                ),
                Expanded(child: Divider(color: context.borderC)),
              ]).animate(delay: 600.ms).fadeIn(duration: 400.ms),

              const SizedBox(height: 24),

              _SocialButtons()
                  .animate(delay: 700.ms)
                  .fadeIn(duration: 400.ms),

              const SizedBox(height: 40),

              Center(
                child: RichText(
                  text: TextSpan(
                    text: "Don't have an account? ",
                    style: TextStyle(color: context.textSec),
                    children: [
                      WidgetSpan(
                        child: GestureDetector(
                          onTap: () => context.go(RouteNames.signup),
                          child: const Text(
                            'Sign Up',
                            style: TextStyle(
                              color: AppColors.primary,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ).animate(delay: 800.ms).fadeIn(duration: 400.ms),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 52,
          height: 52,
          decoration: BoxDecoration(
            gradient: const LinearGradient(colors: AppColors.cyanGradient),
            borderRadius: BorderRadius.circular(14),
            boxShadow: [
              BoxShadow(
                color: AppColors.primary.withValues(alpha: 0.3),
                blurRadius: 16,
              ),
            ],
          ),
          child: const Icon(Icons.hub_rounded, color: Colors.white, size: 28),
        ).animate().scale(
              begin: const Offset(0.5, 0.5),
              end: const Offset(1.0, 1.0),
              duration: 500.ms,
              curve: Curves.easeOutBack,
            ),

        const SizedBox(height: 24),

        Text(
          'Welcome back',
          style: TextStyle(
            color: context.textPri,
            fontSize: 30,
            fontWeight: FontWeight.w800,
            letterSpacing: -0.8,
          ),
        ).animate(delay: 100.ms).fadeIn(duration: 400.ms).slideX(
              begin: -0.1,
              end: 0,
              duration: 400.ms,
            ),

        const SizedBox(height: 6),

        Text(
          'Sign in to your GlucoTwin account',
          style: TextStyle(
            color: context.textSec,
            fontSize: 15,
          ),
        ).animate(delay: 200.ms).fadeIn(duration: 400.ms),
      ],
    );
  }

  Widget _buildForm(BuildContext context) {
    return Column(
      children: [
        TextFormField(
          controller: _emailCtrl,
          keyboardType: TextInputType.emailAddress,
          decoration: const InputDecoration(
            labelText: 'Email Address',
            prefixIcon: Icon(Icons.mail_outline_rounded),
          ),
          validator: (val) {
            if (val == null || val.trim().isEmpty) return 'Email is required';
            final emailRegex = RegExp(r'^[\w\-.]+@([\w\-]+\.)+[\w]{2,}$');
            if (!emailRegex.hasMatch(val.trim())) {
              return 'Enter a valid email address';
            }
            return null;
          },
        ),

        const SizedBox(height: 16),

        TextFormField(
          controller: _passCtrl,
          obscureText: _obscure,
          decoration: InputDecoration(
            labelText: 'Password',
            prefixIcon: const Icon(Icons.lock_outline_rounded),
            suffixIcon: IconButton(
              icon: Icon(
                _obscure
                    ? Icons.visibility_off_rounded
                    : Icons.visibility_rounded,
              ),
              onPressed: () => setState(() => _obscure = !_obscure),
            ),
          ),
          validator: (val) {
            if (val == null || val.isEmpty) return 'Password is required';
            if (val.length < 6) {
              return 'Password must be at least 6 characters';
            }
            return null;
          },
        ),

        const SizedBox(height: 8),

        Align(
          alignment: Alignment.centerRight,
          child: TextButton(
            onPressed: () {},
            child: const Text(
              'Forgot Password?',
              style: TextStyle(color: AppColors.primary, fontSize: 13),
            ),
          ),
        ),
      ],
    );
  }
}

class _BiometricButton extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      height: 56,
      child: OutlinedButton.icon(
        onPressed: () {},
        icon: const Icon(Icons.fingerprint_rounded, size: 24),
        label: const Text(
          'Sign in with Biometrics',
          style: TextStyle(fontSize: 15, fontWeight: FontWeight.w500),
        ),
        style: OutlinedButton.styleFrom(
          foregroundColor: AppColors.primary,
          side: BorderSide(color: context.borderC),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppSpacing.radiusLg),
          ),
        ),
      ),
    );
  }
}

class _SocialButtons extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
            child: _SocialBtn(
                label: 'Google', icon: Icons.g_mobiledata_rounded)),
        const SizedBox(width: 12),
        Expanded(
            child:
                _SocialBtn(label: 'Apple', icon: Icons.apple_rounded)),
      ],
    );
  }
}

class _SocialBtn extends StatelessWidget {
  const _SocialBtn({required this.label, required this.icon});

  final String label;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 52,
      child: OutlinedButton.icon(
        onPressed: () {},
        icon: Icon(icon, size: 22),
        label: Text(label, style: const TextStyle(fontSize: 14)),
        style: OutlinedButton.styleFrom(
          foregroundColor: context.textPri,
          side: BorderSide(color: context.borderC),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppSpacing.radiusLg),
          ),
        ),
      ),
    );
  }
}
