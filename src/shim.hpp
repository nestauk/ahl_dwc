#pragma once
#include <vector>
#include <string>
#include <cmath>
#include <algorithm>
#include <iostream>
#include <random>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/numpy.h>

namespace py = pybind11;

// --- 0. Slice Support ---
struct Slice
{
};
static const Slice _;

// --- 1. RNG Control (NEW) ---
// Singleton pattern for the generator so it's shared across all C++ files
inline std::mt19937 &get_rng()
{
    // Initialize with a random seed by default
    static std::random_device rd;
    static std::mt19937 gen(rd());
    return gen;
}

// Exposed function to set the seed
inline void set_seed(int seed)
{
    get_rng().seed(seed);
}

// R replacement: rnorm
inline void fill_rnorm(double *ptr, size_t n, double mean = 0.0, double sd = 1.0)
{
    std::normal_distribution<> d(mean, sd);
    auto &gen = get_rng();
    for (size_t i = 0; i < n; ++i)
        ptr[i] = d(gen);
}

// --- 2. NumericVector ---
class NumericVector : public std::vector<double>
{
public:
    // Inherit std::vector's constructors: (), (n), (n, v), initializer_list,
    // iterator range, copy and move. We deliberately do NOT redeclare the (n)
    // and (n, v) constructors here: doing so made calls like NumericVector(int, 0.0)
    // ambiguous under GCC/libstdc++ (the inherited fill ctor vs the redeclared one),
    // which broke Linux builds while compiling fine under Clang/libc++. The inherited
    // ctors are behaviourally identical (vector(n) value-initialises to 0.0).
    using std::vector<double>::vector;
    NumericVector(const std::vector<double> &v) : std::vector<double>(v) {}

    double &operator()(size_t i) { return (*this)[i]; }
    double operator()(size_t i) const { return (*this)[i]; }
    void fill(double v) { std::fill(this->begin(), this->end(), v); }

    operator py::object() const
    {
        return py::cast(static_cast<const std::vector<double> &>(*this));
    }
};

// Helper for rnorm returning a vector
inline NumericVector rnorm(int n, double mean = 0.0, double sd = 1.0)
{
    NumericVector res(n);
    fill_rnorm(res.data(), n, mean, sd);
    return res;
}

// Math Operators
template <typename Op>
NumericVector bin_op(const NumericVector &a, const NumericVector &b, Op op)
{
    size_t n = a.size();
    NumericVector res(n);
    for (size_t i = 0; i < n; ++i)
        res[i] = op(a[i], b[i]);
    return res;
}
template <typename Op>
NumericVector scal_op(const NumericVector &a, double b, Op op)
{
    size_t n = a.size();
    NumericVector res(n);
    for (size_t i = 0; i < n; ++i)
        res[i] = op(a[i], b);
    return res;
}
template <typename Op>
NumericVector scal_op_lhs(double a, const NumericVector &b, Op op)
{
    size_t n = b.size();
    NumericVector res(n);
    for (size_t i = 0; i < n; ++i)
        res[i] = op(a, b[i]);
    return res;
}

#define DEF_OP(OP, FUNC)                                                                                                           \
    inline NumericVector operator OP(const NumericVector &a, const NumericVector &b) { return bin_op(a, b, std::FUNC<double>()); } \
    inline NumericVector operator OP(const NumericVector &a, double b) { return scal_op(a, b, std::FUNC<double>()); }              \
    inline NumericVector operator OP(double a, const NumericVector &b) { return scal_op_lhs(a, b, std::FUNC<double>()); }

DEF_OP(+, plus)
DEF_OP(-, minus)
DEF_OP(*, multiplies)
DEF_OP(/, divides)

inline NumericVector pow(const NumericVector &base, double exp)
{
    NumericVector res(base.size());
    for (size_t i = 0; i < base.size(); ++i)
        res[i] = std::pow(base[i], exp);
    return res;
}
inline NumericVector exp(const NumericVector &v)
{
    NumericVector res(v.size());
    for (size_t i = 0; i < v.size(); ++i)
        res[i] = std::exp(v[i]);
    return res;
}
inline NumericVector log(const NumericVector &v)
{
    NumericVector res(v.size());
    for (size_t i = 0; i < v.size(); ++i)
        res[i] = std::log(v[i]);
    return res;
}

// --- 3. NumericMatrix ---
class NumericMatrix
{
public:
    std::vector<double> data;
    int rows, cols;

    NumericMatrix() : rows(0), cols(0) {}
    NumericMatrix(int r, int c) : rows(r), cols(c), data(r * c, 0.0) {}

    NumericMatrix(const std::vector<std::vector<double>> &in)
    {
        rows = in.size();
        cols = (rows > 0) ? in[0].size() : 0;
        data.resize(rows * cols);
        for (int i = 0; i < rows; ++i)
            for (int j = 0; j < cols; ++j)
                data[i * cols + j] = in[i][j];
    }

    int nrow() const { return rows; }
    int ncol() const { return cols; }
    double &operator()(int i, int j) { return data[i * cols + j]; }

    struct ColProxy
    {
        NumericMatrix &m;
        int col;
        void operator=(const NumericVector &v)
        {
            for (int i = 0; i < m.rows; ++i)
                m(i, col) = v[i];
        }
        operator NumericVector() const
        {
            NumericVector res(m.rows);
            for (int i = 0; i < m.rows; ++i)
                res[i] = m(i, col);
            return res;
        }
        // Support += for Brownian loop: W(_, i) = W(_, i-1) + rnorm(...)
        void operator=(const NumericMatrix::ColProxy &other)
        {
            NumericVector v = other;
            for (int i = 0; i < m.rows; ++i)
                m(i, col) = v[i];
        }
    };

    NumericVector operator()(int r, Slice) const
    {
        if (r < 0 || r >= rows)
            return NumericVector(cols, 0.0);
        NumericVector res(cols);
        for (int j = 0; j < cols; ++j)
            res[j] = data[r * cols + j];
        return res;
    }
    ColProxy operator()(Slice, int c) { return ColProxy{*this, c}; }

    operator py::object() const
    {
        return py::array_t<double>(
            {rows, cols},
            {cols * sizeof(double), sizeof(double)},
            data.data());
    }
};

// --- 4. String Helpers ---
class StringVector : public std::vector<std::string>
{
public:
    using std::vector<std::string>::vector;
    StringVector(int n) : std::vector<std::string>(n) {}
    std::string &operator()(size_t i) { return (*this)[i]; }
    operator py::object() const { return py::cast(static_cast<const std::vector<std::string> &>(*this)); }
};

class StringMatrix
{
public:
    std::vector<std::string> data;
    int rows, cols;
    StringMatrix(int r, int c) : rows(r), cols(c), data(r * c) {}
    std::string &operator()(int i, int j) { return data[i * cols + j]; }
    struct ColProxy
    {
        StringMatrix &m;
        int col;
        void operator=(const StringVector &v)
        {
            for (int i = 0; i < m.rows && i < (int)v.size(); ++i)
                m.data[i * m.cols + col] = v[i];
        }
    };
    ColProxy operator()(Slice, int c) { return ColProxy{*this, c}; }
    operator py::object() const
    {
        py::list out;
        for (int i = 0; i < rows; ++i)
        {
            py::list row;
            for (int j = 0; j < cols; ++j)
                row.append(data[i * cols + j]);
            out.append(row);
        }
        return out;
    }
};

// --- 5. Named/List ---
struct Named
{
    const char *name;
    py::object value;
    template <typename T>
    Named(const char *n, const T &v) : name(n), value(py::cast(v)) {}
    Named(const char *n, const NumericMatrix &v) : name(n), value(v) {}
    Named(const char *n, const StringMatrix &v) : name(n), value(v) {}
    Named(const char *n, const NumericVector &v) : name(n), value(v) {}
    Named(const char *n, const StringVector &v) : name(n), value(v) {}
};
struct NamedBuilder
{
    const char *key;
    template <typename T>
    Named operator=(const T &val) { return Named(key, val); }
};
inline NamedBuilder Named(const char *n) { return NamedBuilder{n}; }

class List : public py::dict
{
public:
    using py::dict::dict;
    static void pack(List &) {}
    template <typename... Args>
    static void pack(List &d, struct Named n, Args... args)
    {
        d[n.name] = n.value;
        pack(d, args...);
    }
    template <typename... Args>
    static List create(Args... args)
    {
        List d;
        pack(d, args...);
        return d;
    }
};

#define Rcout std::cout
