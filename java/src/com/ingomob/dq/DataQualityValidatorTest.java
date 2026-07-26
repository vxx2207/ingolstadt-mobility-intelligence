package com.ingomob.dq;

/** Minimal dependency-free unit tests for the data-quality validator. */
public class DataQualityValidatorTest {

    static int failures = 0;

    static void check(boolean cond, String msg) {
        if (!cond) {
            failures++;
            System.out.println("FAIL: " + msg);
        } else {
            System.out.println("ok:   " + msg);
        }
    }

    public static void main(String[] args) {
        check(DataQualityValidator.inBox(48.7665, 11.4258), "city center within bbox");
        check(!DataQualityValidator.inBox(52.52, 13.40), "Berlin rejected by bbox");
        check(DataQualityValidator.pi("42") == 42, "parse valid int");
        check(DataQualityValidator.pi("x") == -1, "invalid int -> -1");
        check(Double.isNaN(DataQualityValidator.pd("oops")), "invalid double -> NaN");

        DataQualityValidator.Check c = new DataQualityValidator.Check("demo", "tbl");
        c.record(true, "ok");
        c.record(false, "bad-1");
        c.record(false, "bad-2");
        check(c.passed == 1 && c.failed == 2, "record() tallies pass/fail");
        check(c.samples.size() == 2, "records sample issues");

        if (failures > 0) {
            System.err.println(failures + " test(s) failed");
            System.exit(1);
        }
        System.out.println("ALL JAVA TESTS PASSED");
    }
}
