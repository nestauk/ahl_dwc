#include "adult_weight.h"
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

// Forward declaration for EnergyBuilder
NumericMatrix EnergyBuilder(NumericMatrix Energy, NumericVector Time, std::string interpol);

namespace py = pybind11;

// Helper Converters
NumericMatrix to_mat(const std::vector<std::vector<double>> &in) { return NumericMatrix(in); }
NumericVector to_vec(const std::vector<double> &in) { return NumericVector(in); }

// Wrapper Functions for Adult Weight
py::dict py_adult_weight(std::vector<double> bw, std::vector<double> ht, std::vector<double> age,
                         std::vector<double> sex, std::vector<std::vector<double>> EIchange,
                         std::vector<std::vector<double>> NAchange, std::vector<double> PAL,
                         std::vector<double> pcarb_base, std::vector<double> pcarb, double dt, double days,
                         bool checkValues)
{
    Adult Person(to_vec(bw), to_vec(ht), to_vec(age), to_vec(sex), to_mat(EIchange), to_mat(NAchange), to_vec(PAL),
                 to_vec(pcarb), to_vec(pcarb_base), dt, checkValues);
    return Person.rk4(days);
}

py::dict py_adult_weight_EI(std::vector<double> bw, std::vector<double> ht, std::vector<double> age,
                            std::vector<double> sex, std::vector<std::vector<double>> EIchange,
                            std::vector<std::vector<double>> NAchange, std::vector<double> PAL,
                            std::vector<double> pcarb_base, std::vector<double> pcarb, double dt,
                            std::vector<double> extradata, double days, bool checkValues, bool isEnergy)
{
    Adult Person(to_vec(bw), to_vec(ht), to_vec(age), to_vec(sex), to_mat(EIchange), to_mat(NAchange), to_vec(PAL),
                 to_vec(pcarb), to_vec(pcarb_base), dt, to_vec(extradata), checkValues, isEnergy);
    return Person.rk4(days);
}

py::dict py_adult_weight_EI_fat(std::vector<double> bw, std::vector<double> ht, std::vector<double> age,
                                std::vector<double> sex, std::vector<std::vector<double>> EIchange,
                                std::vector<std::vector<double>> NAchange, std::vector<double> PAL,
                                std::vector<double> pcarb_base, std::vector<double> pcarb, double dt,
                                std::vector<double> input_EI, std::vector<double> input_fat, double days,
                                bool checkValues)
{
    Adult Person(to_vec(bw), to_vec(ht), to_vec(age), to_vec(sex), to_mat(EIchange), to_mat(NAchange), to_vec(PAL),
                 to_vec(pcarb), to_vec(pcarb_base), dt, to_vec(input_EI), to_vec(input_fat), checkValues);
    return Person.rk4(days);
}

py::object py_energy_builder(std::vector<std::vector<double>> energy, std::vector<double> time, std::string interpol)
{
    NumericMatrix mat = to_mat(energy);
    NumericVector vec = to_vec(time);
    NumericMatrix result = EnergyBuilder(mat, vec, interpol);
    return result;
}

PYBIND11_MODULE(_core, m)
{
    m.def("adult_weight_wrapper", &py_adult_weight);
    m.def("adult_weight_wrapper_EI", &py_adult_weight_EI);
    m.def("adult_weight_wrapper_EI_fat", &py_adult_weight_EI_fat);
    m.def("EnergyBuilder", &py_energy_builder);
    m.def("set_seed", &set_seed, "Set the C++ random seed");
}
