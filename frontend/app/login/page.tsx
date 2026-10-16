
"use client";

import { useRef, useState } from "react";
import type { FormEvent } from "react";
import Link from "next/link";

import { api, ApiError } from "@/lib/api";
import type { User } from "@/lib/api";


type LoginForm = {
  email: string;
  password: string;
};

type LoginErrors = {
  email?: string;
  password?: string;
};

const initialForm: LoginForm = {
  email: "",
  password: "",
};


function validateLogin(values: LoginForm): LoginErrors {
  const errors: LoginErrors = {};

  const email = values.email.trim();

  if (!email) {
    errors.email = "Email is required.";
  } else if (
    !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
  ) {
    errors.email = "Enter a valid email address.";
  }

  if (!values.password) {
    errors.password = "Password is required.";
  } else if (
    values.password.length > 128 ||
    new TextEncoder().encode(values.password).length > 256
  ) {
    errors.password = "Password exceeds the allowed length.";
  }

  return errors;
}


export default function LoginPage() {
  const [values, setValues] = useState<LoginForm>(
    initialForm
  );

  const [errors, setErrors] = useState<LoginErrors>({});
  const [serverError, setServerError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const [authenticatedUser, setAuthenticatedUser] =
    useState<User | null>(null);

  // Prevent duplicate requests even before React re-renders.
  const submissionInProgress = useRef(false);

  function updateField(
    field: keyof LoginForm,
    value: string
  ) {
    setValues((previous) => ({
      ...previous,
      [field]: value,
    }));

    setErrors((previous) => ({
      ...previous,
      [field]: undefined,
    }));

    setServerError("");
  }

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>
  ) {
    event.preventDefault();

    if (submissionInProgress.current) {
      return;
    }

    const validationErrors = validateLogin(values);

    setErrors(validationErrors);
    setServerError("");

    if (Object.keys(validationErrors).length > 0) {
      return;
    }

    submissionInProgress.current = true;
    setIsSubmitting(true);

    try {
      // 1. Authenticate credentials with FastAPI.
      const result = await api.login({
        email: values.email.trim().toLowerCase(),
        password: values.password,
      });

      // 2. Use the JWT immediately to verify
      //    the authenticated user.
      const user = await api.getMe(
        result.access_token
      );

      // 3. Keep only safe user information in
      //    React state. Do not retain the JWT.
      setAuthenticatedUser(user);

      // 4. Clear password after successful login.
      setValues(initialForm);

    } catch (error) {
      if (error instanceof ApiError) {
        if (error.status === 401) {
          setServerError(
            "Invalid email or password."
          );
        } else if (error.status === 422) {
          setServerError(
            "Please check your login details."
          );
        } else {
          setServerError(error.message);
        }
      } else {
        setServerError(
          "Unable to connect to the server. Please try again."
        );
      }
    } finally {
      submissionInProgress.current = false;
      setIsSubmitting(false);
    }
  }

  if (authenticatedUser) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-12 text-slate-900">
        <section className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
          <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-full bg-green-100 text-2xl text-green-700">
            ✓
          </div>

          <h1 className="text-2xl font-bold">
            Login successful
          </h1>

          <p className="mt-3 text-sm text-slate-600">
            FastAPI has authenticated your credentials
            and verified your access token.
          </p>

          <div className="mt-6 rounded-xl bg-slate-50 p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
              Authenticated user
            </p>

            <p className="mt-2 break-all font-medium">
              {authenticatedUser.email}
            </p>

            <p className="mt-1 break-all text-xs text-slate-500">
              User ID: {authenticatedUser.id}
            </p>
          </div>

          <p className="mt-5 text-sm leading-6 text-slate-600">
            This is a temporary authentication
            verification screen. We have not saved
            your JWT or created a persistent session.
            Refreshing this page will return you to
            the login form.
          </p>

          <button
            type="button"
            onClick={() => {
              setAuthenticatedUser(null);
              setValues(initialForm);
              setServerError("");
              setErrors({});
            }}
            className="mt-6 w-full rounded-lg bg-slate-900 px-4 py-3 text-sm font-semibold text-white hover:bg-slate-800"
          >
            Return to login
          </button>
        </section>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-12 text-slate-900">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <Link
            href="/"
            className="text-sm font-semibold text-slate-600 hover:text-slate-900"
          >
            File Vault
          </Link>

          <h1 className="mt-4 text-3xl font-bold tracking-tight">
            Welcome back
          </h1>

          <p className="mt-2 text-sm text-slate-600">
            Sign in to your File Vault account.
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          noValidate
          className="space-y-5 rounded-2xl border border-slate-200 bg-white p-7 shadow-sm"
        >
          <div>
            <label
              htmlFor="email"
              className="mb-2 block text-sm font-medium"
            >
              Email address
            </label>

            <input
              id="email"
              type="email"
              name="email"
              autoComplete="email"
              placeholder="you@example.com"
              value={values.email}
              onChange={(event) =>
                updateField("email", event.target.value)
              }
              disabled={isSubmitting}
              aria-invalid={Boolean(errors.email)}
              aria-describedby={
                errors.email ? "email-error" : undefined
              }
              className="w-full rounded-lg border border-slate-300 px-3 py-3 text-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-200 disabled:opacity-60"
            />

            {errors.email && (
              <p
                id="email-error"
                role="alert"
                className="mt-2 text-sm text-red-600"
              >
                {errors.email}
              </p>
            )}
          </div>

          <div>
            <label
              htmlFor="password"
              className="mb-2 block text-sm font-medium"
            >
              Password
            </label>

            <div className="relative">
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                name="password"
                autoComplete="current-password"
                placeholder="Enter your password"
                value={values.password}
                onChange={(event) =>
                  updateField(
                    "password",
                    event.target.value
                  )
                }
                disabled={isSubmitting}
                aria-invalid={Boolean(errors.password)}
                aria-describedby={
                  errors.password
                    ? "password-error"
                    : undefined
                }
                className="w-full rounded-lg border border-slate-300 px-3 py-3 pr-20 text-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-200 disabled:opacity-60"
              />

              <button
                type="button"
                onClick={() =>
                  setShowPassword((previous) => !previous)
                }
                disabled={isSubmitting}
                aria-label={
                  showPassword
                    ? "Hide password"
                    : "Show password"
                }
                className="absolute inset-y-0 right-3 text-xs font-medium text-slate-600 hover:text-slate-900"
              >
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>

            {errors.password && (
              <p
                id="password-error"
                role="alert"
                className="mt-2 text-sm text-red-600"
              >
                {errors.password}
              </p>
            )}
          </div>

          {serverError && (
            <div
              role="alert"
              aria-live="polite"
              className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700"
            >
              {serverError}
            </div>
          )}

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full rounded-lg bg-slate-900 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSubmitting
              ? "Signing in..."
              : "Sign in"}
          </button>

          <p className="text-center text-sm text-slate-600">
            Don&apost have an account?{" "}
            <Link
              href="/register"
              className="font-semibold text-slate-900 underline underline-offset-4"
            >
              Create account
            </Link>
          </p>
        </form>
      </div>
    </main>
  );
}
