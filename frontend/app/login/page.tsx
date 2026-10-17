
"use client";

import { useRef, useState } from "react";
import type { FormEvent } from "react";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/lib/api";


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
    errors.password =
      "Password exceeds the allowed length.";
  }

  return errors;
}


export default function LoginPage() {
  const router = useRouter();

  const {
    login,
    isLoading,
    isAuthenticated,
  } = useAuth();

  const [values, setValues] =
    useState<LoginForm>(initialForm);

  const [errors, setErrors] =
    useState<LoginErrors>({});

  const [serverError, setServerError] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const submittingRef = useRef(false);


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

    if (
      submittingRef.current ||
      isLoading ||
      isAuthenticated
    ) {
      return;
    }

    const validationErrors = validateLogin(values);

    setErrors(validationErrors);
    setServerError("");

    if (Object.keys(validationErrors).length > 0) {
      return;
    }

    submittingRef.current = true;

    try {
      // AuthContext handles:
      // 1. Verify email and password through FastAPI.
      // 2. Receive JWT.
      // 3. Call /auth/me to retrieve the user.
      // 4. Store the session in React memory.
      // 5. Manage token expiration.
      await login({
        email: values.email.trim().toLowerCase(),
        password: values.password,
      });

      // Clear sensitive form input after login.
      setValues(initialForm);

      // Client-side navigation preserves AuthProvider.
      router.replace("/dashboard");

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
      } else if (
        error instanceof Error &&
        error.message ===
          "A login request is already in progress."
      ) {
        setServerError(
          "A login request is already in progress."
        );
      } else {
        setServerError(
          "Unable to complete login. Please try again."
        );
      }
    } finally {
      submittingRef.current = false;
    }
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

          {/* Email */}

          <div>
            <label
              htmlFor="email"
              className="mb-2 block text-sm font-medium"
            >
              Email address
            </label>

            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              value={values.email}
              onChange={(event) =>
                updateField("email", event.target.value)
              }
              disabled={isLoading}
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

          {/* Password */}

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
                name="password"
                type={
                  showPassword ? "text" : "password"
                }
                autoComplete="current-password"
                placeholder="Enter your password"
                value={values.password}
                onChange={(event) =>
                  updateField(
                    "password",
                    event.target.value
                  )
                }
                disabled={isLoading}
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
                  setShowPassword(
                    (previous) => !previous
                  )
                }
                disabled={isLoading}
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

          {/* API error */}

          {serverError && (
            <div
              role="alert"
              aria-live="polite"
              className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700"
            >
              {serverError}
            </div>
          )}

          {/* Submit */}

          <button
            type="submit"
            disabled={isLoading || isAuthenticated}
            className="w-full rounded-lg bg-slate-900 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isLoading
              ? "Signing in..."
              : isAuthenticated
                ? "Signed in"
                : "Sign in"}
          </button>

          <p className="text-center text-sm text-slate-600">
            Don&apos;t have an account?{" "}
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
